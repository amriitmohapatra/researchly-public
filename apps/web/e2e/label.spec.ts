/**
 * S4c: the Label page (/label), the S4 exit check's tool, on the build
 * without accounts (it works signed in or not). The engine is mocked; the
 * paragraph is synthetic. Labels persist in this browser, text never does,
 * and the export is exactly what ml/eval/label_precision.py reads.
 */
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { AnalyzeRequest, Suggestion } from "@researchly/contract";
import { ENGINE, happyResponse } from "./fixtures";
import { json } from "./helpers";

const PARAGRAPH = "We fitted a renewal model to weekly counts. It is clearly proven that the the intervention worked.";

function sugg(id: string, rule_id: string, category: Suggestion["category"], needle: string, message: string): Suggestion {
  const content = `Discussion\n\n${PARAGRAPH}\n`;
  const start = content.indexOf(needle);
  return {
    id,
    rule_id,
    rule_name: rule_id,
    category,
    tier: "craft",
    span: { start, end: start + needle.length, line: 3, col: 1 },
    section: "discussion",
    message,
    why: "A synthetic explanation.",
    plain: "In everyday words: a synthetic explanation for the labelling suite.",
    source: "A named source (Researchly notes)",
    learn_ref: null,
    replacement: null,
    fix_safety: "review",
    confidence: 1,
    text: needle,
  };
}

const CARDS = [
  sugg("l-1", "C201", "convention", "clearly proven", "‘clearly proven’ claims more certainty than the evidence can carry."),
  sugg("l-2", "S010", "correction", "the the", "‘the’ is repeated."),
];

async function mockLabelEngine(page: Page): Promise<AnalyzeRequest[]> {
  const seen: AnalyzeRequest[] = [];
  await page.route(`${ENGINE}/v1/analyze`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" } });
    const body = route.request().postDataJSON() as AnalyzeRequest;
    seen.push(body);
    return json(route, 200, { ...happyResponse, suggestions: CARDS, counts: { convention: 1, correction: 1 }, hidden_preferences: 0 });
  });
  return seen;
}

async function axeSerious(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
  return r.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`);
}

test.describe("Label flags", () => {
  test("check a paragraph under its section, label each flag, move on, reload, and export the file the script reads", async ({ page }) => {
    const seen = await mockLabelEngine(page);
    await page.goto("/label");
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 1. 0 of 50 paragraphs, 0 flags labelled.");
    // The guide's three verdicts, paraphrased on the page.
    await page.getByTestId("label-help").locator("summary").click();
    await expect(page.getByTestId("label-help")).toContainText("A false flag");
    await expect(page.getByTestId("label-help").getByRole("link", { name: "the labelling guide" })).toHaveAttribute("href", /labelling-guide\.md$/);

    // Nothing to check: said, nothing sent.
    await page.getByTestId("label-check").click();
    await expect(page.getByTestId("label-problem")).toContainText("Paste one paragraph");
    expect(seen).toHaveLength(0);

    await page.getByTestId("label-section").selectOption("discussion");
    await page.getByTestId("label-paragraph").fill(PARAGRAPH);
    await page.getByTestId("label-check").click();
    await expect(page.getByTestId("label-card")).toHaveCount(2);
    expect(seen[0]!.content).toBe(`Discussion\n\n${PARAGRAPH}\n`);
    expect(seen[0]!.format).toBe("plain");
    expect(seen[0]!.options?.mode).toBe("revise");

    const first = page.getByTestId("label-card").nth(0);
    await expect(first.getByRole("group", { name: "Your verdict on this flag" }).getByRole("button")).toHaveText(["Useful", "Wrong", "Unsure"]);
    await first.getByTestId("verdict-wrong").click();
    await expect(first.getByTestId("verdict-wrong")).toHaveAttribute("aria-pressed", "true");
    // A changed mind replaces the label.
    await first.getByTestId("verdict-useful").click();
    await expect(first.getByTestId("verdict-useful")).toHaveAttribute("aria-pressed", "true");
    await expect(first.getByTestId("verdict-wrong")).toHaveAttribute("aria-pressed", "false");
    await page.getByTestId("label-card").nth(1).getByTestId("verdict-unsure").click();
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 1. 1 of 50 paragraphs, 2 flags labelled.");

    // Next paragraph clears the text and the cards.
    await page.getByTestId("label-next").click();
    await expect(page.getByTestId("label-paragraph")).toHaveValue("");
    await expect(page.getByTestId("label-card")).toHaveCount(0);
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 2. 1 of 50 paragraphs, 2 flags labelled.");

    await page.getByTestId("label-section").selectOption("methods");
    await page.getByTestId("label-paragraph").fill(PARAGRAPH);
    await page.getByTestId("label-check").click();
    await page.getByTestId("label-card").nth(1).getByTestId("verdict-wrong").click();
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 2. 2 of 50 paragraphs, 3 flags labelled.");

    // A reload keeps the labels; the paragraph is gone, and never stored.
    await page.reload();
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 2. 2 of 50 paragraphs, 3 flags labelled.");
    await expect(page.getByTestId("label-paragraph")).toHaveValue("");
    const stored = await page.evaluate(() => ({ keys: Object.keys(localStorage), all: JSON.stringify(localStorage) }));
    expect(stored.keys).toEqual(["researchly.labels"]);
    expect(stored.all).not.toContain("renewal");
    expect(stored.all).not.toContain("clearly");
    expect(await page.evaluate(() => sessionStorage.length)).toBe(0);

    const download = page.waitForEvent("download");
    await page.getByTestId("label-export").click();
    const file = await download;
    expect(file.suggestedFilename()).toBe("researchly-labels.json");
    const data = JSON.parse(readFileSync((await file.path())!, "utf8"));
    expect(data).toEqual({
      version: 1,
      labels: [
        { paragraph: 1, rule_id: "C201", category: "convention", section: "discussion", verdict: "useful" },
        { paragraph: 1, rule_id: "S010", category: "correction", section: "discussion", verdict: "unsure" },
        { paragraph: 2, rule_id: "S010", category: "correction", section: "methods", verdict: "wrong" },
      ],
    });
    expect(JSON.stringify(data)).not.toContain("the the");

    // Start over, after a confirmation that focuses the safe choice.
    await page.getByTestId("label-clear-open").click();
    await expect(page.getByTestId("label-clear-dialog").getByRole("button", { name: "Keep them" })).toBeFocused();
    await page.getByTestId("label-clear-confirm").click();
    await expect(page.getByTestId("label-count")).toHaveText("Paragraph 1. 0 of 50 paragraphs, 0 flags labelled.");
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  });

  test("a paragraph with no flags says to skip it", async ({ page }) => {
    await page.route(`${ENGINE}/v1/analyze`, async (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" } });
      return json(route, 200, { ...happyResponse, suggestions: [], counts: {}, hidden_preferences: 0 });
    });
    await page.goto("/label");
    await page.getByTestId("label-paragraph").fill("A short paragraph with nothing to flag.");
    await page.getByTestId("label-check").click();
    await expect(page.getByTestId("label-empty")).toContainText("skipped");
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`375px, ${scheme}: no horizontal scroll, no serious axe violations with cards labelled`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 800 });
      await mockLabelEngine(page);
      await page.goto("/label");
      await page.getByTestId("label-help").locator("summary").click();
      await page.getByTestId("label-paragraph").fill(PARAGRAPH);
      await page.getByTestId("label-check").click();
      await page.getByTestId("label-card").nth(0).getByTestId("verdict-useful").click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      expect(await axeSerious(page)).toEqual([]);
    });
  }
});
