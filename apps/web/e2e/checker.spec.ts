import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { DOCUMENT_TYPES, LEARN_CARDS, MAX_CONTENT_CHARS, READING_KEY } from "@researchly/contract";
import {
  CHECKLIST,
  CHECKLISTS,
  COMMENTARY_NOTE,
  compoundSuggestion,
  degradedGrammarResponse,
  emptyResponse,
  error413,
  error422,
  error429,
  error500,
  GUESS_EVIDENCE,
  happyResponse,
  NARRATIVE,
  PROFILES,
  REVIEW,
  REVIEW_DISCLAIMER,
  SAMPLE_TEXT,
  withDocumentWideResponse,
  withPreferencesResponse,
} from "./fixtures";
import { check, isReddish, json, mockEngine, paste, recordOwnOriginRequests, rgb } from "./helpers";

const byRule = (id: string) => withPreferencesResponse.suggestions.find((s) => s.rule_id === id)!;
const mark = (page: import("@playwright/test").Page, id: string) =>
  page.getByTestId("document").locator(`[data-sids~="${id}"]`);

test.describe("happy path", () => {
  test("highlights the right characters, lists cards, expands Why", async ({ page, baseURL }) => {
    const sent = await mockEngine(page);
    const own = recordOwnOriginRequests(page, baseURL!);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);

    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();

    // The request carries exactly the text, straight to the engine.
    expect(sent).toHaveLength(1);
    expect(sent[0]).toEqual({
      content: SAMPLE_TEXT,
      format: "plain",
      options: { show_preferences: false, document_type: "auto", review: true, narrative: true, mode: "revise" },
    });
    // ...and nothing went to the Next.js server except page/asset GETs.
    expect(own.filter((r) => r.method() !== "GET")).toEqual([]);
    expect(own.some((r) => (r.postData() ?? "").includes("Dengue"))).toBe(false);

    // Spans after the emoji and the non-BMP 𝑅 land on the right characters.
    for (const s of happyResponse.suggestions.filter((x) => x.text)) {
      await expect(mark(page, s.id).first()).toBeVisible();
      const covered = (await mark(page, s.id).allTextContents()).join("");
      expect(covered, s.rule_id).toBe(s.text);
    }
    // The zero-length span renders as an insertion point.
    await expect(mark(page, byRule("G110").id)).toHaveClass(/pt-correction/);
    // The whole submitted text is rendered (as text), not just the flagged parts.
    await expect(page.getByTestId("document")).toContainText(SAMPLE_TEXT.trim().slice(0, 40));

    const cards = page.getByTestId("suggestion-card");
    await expect(cards).toHaveCount(8);
    await expect(page.getByTestId("filter-all")).toContainText("8");
    await expect(page.getByTestId("filter-correction")).toContainText("2");
    await expect(page.getByTestId("filter-convention")).toContainText("2");

    const first = cards.first();
    await expect(first).toContainText("Improvement");
    await expect(first).toContainText("Introduction");
    await expect(first).toContainText("clearly proven");
    // The explanation in everyday words is open from the start; the technical account is one click away.
    await expect(first.getByTestId("card-plain")).toContainText("In everyday words");
    await expect(first.getByText(/Hyland \(2005\)/)).toBeVisible();
    await expect(first.getByText(/Boosters such as/)).toBeHidden();
    await first.getByText("The full reasoning").click();
    await expect(first.getByText(/Boosters such as/)).toBeVisible();

    // A replacement is labelled as a suggestion; there is no apply button.
    const wordy = page.locator(`#card-${byRule("C120").id}`);
    await expect(wordy).toContainText("Suggested revision (your call):");
    await expect(page.getByRole("button", { name: /apply|accept|fix/i })).toHaveCount(0);

    // Card → highlight
    await wordy.getByRole("button", { name: "Show in text" }).click();
    await expect(mark(page, byRule("C120").id)).toBeFocused();
    await expect(mark(page, byRule("C120").id)).toHaveClass(/is-active/);

    // Highlight → card
    await mark(page, byRule("V310").id).click();
    await expect(page.locator(`#card-${byRule("V310").id}`)).toBeFocused();
    await expect(page.locator(`#card-${byRule("V310").id}`)).toHaveClass(/is-active/);

    // Read-outs, not a score.
    await expect(page.getByRole("heading", { name: "Read-outs" })).toBeVisible();
    await expect(page.getByText("Read-outs, not a score.", { exact: false })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/overall score|grade/i);

    // No banner for the missing learned tier.
    await expect(page.getByTestId("health-banner")).toHaveCount(0);
  });

  test("filters by category", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("filter-convention").click();
    await expect(page.getByTestId("filter-convention")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("suggestion-card")).toHaveCount(2);
    await expect(page.getByTestId("document").locator("mark")).toHaveCount(2);
    await expect(page.locator(".filter-blurb")).toContainText("Not an error");
  });

  test("Ctrl+Enter checks from the editor", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await page.getByLabel("Text to check").press("Control+Enter");
    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();
    expect(sent).toHaveLength(1);
  });

  test("remembers the format (only the format) and sends it", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await page.getByLabel("Format").selectOption("latex");
    await page.reload();
    await expect(page.getByLabel("Format")).toHaveValue("latex");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("results")).toBeVisible();
    expect(sent[0]!.format).toBe("latex");

    // Nothing but the format preference is stored; no cookies at all.
    const stored = await page.evaluate(() => ({
      local: Object.keys(localStorage),
      localValues: Object.values(localStorage).join(""),
      session: Object.keys(sessionStorage),
    }));
    expect(stored.local).toEqual(["researchly.format"]);
    expect(stored.localValues).not.toContain("Dengue");
    expect(stored.session).toEqual([]);
    expect(await page.context().cookies()).toEqual([]);
  });
});

test.describe("cards", () => {
  test("plain explanation first, the full reasoning behind a disclosure, no rule code or tier on show", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const card = page.locator(`#card-${byRule("C120").id}`);
    // Order: message, flagged words, revision, the plain explanation, the disclosure, then the source as a reference.
    const order = await card.evaluate((el) =>
      [".card-msg", ".card-quote", ".card-repl", ".card-plain", "details.why", ".card-source"].map((sel) =>
        Array.from(el.querySelectorAll("*")).indexOf(el.querySelector(sel)!),
      ),
    );
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(order.every((i) => i >= 0)).toBe(true);
    await expect(card.getByTestId("card-plain")).toBeVisible();
    await expect(card.locator("details.why")).not.toHaveAttribute("open");
    await expect(card).toContainText("Source:");
    // The rule id and the tier are data, not copy.
    await expect(card).toHaveAttribute("data-rule", "C120");
    await expect(card).not.toContainText("Rule");
    await expect(card).not.toContainText("Checked by");
    await expect(card).not.toContainText("C120");
    // The only "Checked by" on the page is the footer's engine version, never a tier on a card.
    await expect(page.locator("body")).not.toContainText(/Checked by (?!engine)/);
    await card.getByText("The full reasoning").click();
    await expect(card.locator("details.why")).toHaveAttribute("open", "");
    await expect(card.locator(".why-body")).toContainText(byRule("C120").why);
  });

  test("an older engine without plain explanations shows the reasoning in its place, once", async ({ page }) => {
    const stripped = {
      ...happyResponse,
      suggestions: happyResponse.suggestions.map((s) => ({ ...s, plain: "" })),
    };
    await mockEngine(page, (_r, route) => json(route, 200, stripped));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const card = page.locator(`#card-${byRule("C201").id}`);
    await expect(card.getByTestId("card-plain")).toContainText(/Boosters such as/);
    await expect(card.locator("details.why")).toHaveCount(0);
  });
});

test.describe("sections", () => {
  test("choosing a section lists only its suggestions, with document-wide ones kept under Whole document", async ({ page }) => {
    const sent = await mockEngine(page, (_r, route) => json(route, 200, withDocumentWideResponse));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByRole("heading", { name: "9 suggestions" })).toBeVisible();
    const chooser = page.getByTestId("section-filter");
    await expect(chooser).toHaveValue("all");
    await expect(chooser.locator("option")).toHaveText(["All sections (9)", "Introduction (2)", "Methods (3)", "Discussion (4)"]);
    await expect(page.getByTestId("whole-document")).toHaveCount(0);

    await chooser.selectOption("methods");
    // The whole text was sent once; the filter is instant and client-side.
    expect(sent).toHaveLength(1);
    await expect(page.getByRole("heading", { name: "Suggestions in Methods" })).toBeVisible();
    const inSection = page.locator(".list-col > ol [data-testid=suggestion-card]");
    await expect(inSection).toHaveCount(3);
    for (const el of await inSection.all()) await expect(el).toContainText("Methods");
    const whole = page.getByTestId("whole-document");
    await expect(whole.getByRole("heading", { name: "Whole document" })).toBeVisible();
    await expect(whole.getByTestId("suggestion-card")).toHaveCount(1);
    await expect(whole.getByTestId("suggestion-card")).toHaveAttribute("data-rule", "W211");
    await expect(page.getByTestId("section-blurb")).toContainText("Showing the Methods section");
    // The text column stays whole; only the highlights narrow (two marks, one insertion point, and the document-wide one).
    await expect(page.getByTestId("document")).toContainText("further studies are needed");
    await expect(page.getByTestId("document").locator("mark")).toHaveCount(3);
    await expect(page.getByTestId("document").locator(".pt")).toHaveCount(1);
    await expect(mark(page, compoundSuggestion.id)).toBeVisible();

    // Category and section filters combine.
    await page.getByTestId("filter-convention").click();
    await expect(inSection).toHaveCount(2);
    await expect(whole.getByTestId("suggestion-card")).toHaveCount(1);
    await page.getByTestId("filter-improvement").click();
    await expect(page.getByTestId("no-cards")).toContainText("No improvements in the Methods section.");
    await expect(page.getByTestId("whole-document")).toHaveCount(0);
    await page.getByTestId("filter-all").click();

    // Back to all: one list again.
    await chooser.selectOption("all");
    await expect(page.getByTestId("suggestion-card")).toHaveCount(9);
    await expect(page.getByTestId("whole-document")).toHaveCount(0);

    // A new check starts from "All sections".
    await chooser.selectOption("discussion");
    await expect(inSection).toHaveCount(4);
    await check(page);
    await expect(page.getByTestId("section-filter")).toHaveValue("all");
    await expect(page.getByTestId("suggestion-card")).toHaveCount(9);
    expect(sent).toHaveLength(2);
  });

  test("without a rule registry the engine's document-wide rules are still kept aside", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await mockEngine(page, (_r, route) => json(route, 200, withDocumentWideResponse), null);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("section-filter").selectOption("introduction");
    await expect(page.locator(".list-col > ol [data-testid=suggestion-card]")).toHaveCount(1);
    await expect(page.getByTestId("whole-document").getByTestId("suggestion-card")).toHaveAttribute("data-rule", "W211");
    expect(errors).toEqual([]);
  });
});

test.describe("taxonomy", () => {
  test("conventions look advisory, never red", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const card = page.locator(`#card-${byRule("V310").id}`);
    const badge = card.locator(".badge");
    await expect(badge).toHaveText("Convention");
    const styles = await badge.evaluate((el) => {
      const cs = getComputedStyle(el);
      const c = getComputedStyle(el.closest("article")!);
      return { color: cs.color, bg: cs.backgroundColor, border: c.borderLeftColor };
    });
    const hl = await mark(page, byRule("V310").id).evaluate((el) => getComputedStyle(el).textDecorationColor);
    for (const c of [styles.color, styles.bg, styles.border, hl]) expect(isReddish(rgb(c)), c).toBe(false);
    // Convention highlights use a dotted underline, corrections a solid one (not colour alone).
    expect(await mark(page, byRule("V310").id).evaluate((el) => getComputedStyle(el).textDecorationStyle)).toBe("dotted");
    expect(await mark(page, byRule("S010").id).evaluate((el) => getComputedStyle(el).textDecorationStyle)).toBe("solid");
  });

  test("preferences are hidden by default and shown on request", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const note = page.getByTestId("hidden-prefs");
    await expect(note).toContainText("2 preferences hidden");
    await expect(page.getByTestId("filter-preference")).toHaveCount(0);

    await note.getByRole("button", { name: /show/i }).click();
    await expect(page.getByRole("heading", { name: "10 suggestions" })).toBeVisible();
    expect(sent.at(-1)!.options?.show_preferences).toBe(true);
    await expect(page.getByLabel("Show preferences")).toBeChecked();
    await expect(page.getByTestId("hidden-prefs")).toHaveCount(0);
    await expect(page.getByTestId("filter-preference")).toContainText("2");
    await expect(page.locator('[data-testid="suggestion-card"][data-category="preference"]')).toHaveCount(2);

    // Turning the toggle off hides them again without a request.
    await page.getByLabel("Show preferences").uncheck();
    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();
    await expect(page.getByTestId("hidden-prefs")).toContainText("2 preferences hidden");
    expect(sent).toHaveLength(2);
  });
});

test.describe("article type and the reviewer's brief (S4)", () => {
  test("Check as: sent on every request, re-checks on change, said in the results, remembered as the choice alone", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    const select = page.getByLabel("Check as");
    await expect(select).toHaveValue("auto");
    // The labels come from the engine's registry, in its order; the chosen type's summary reads under the control.
    await expect(select.locator("option")).toHaveText(PROFILES.map((p) => p.label));
    await expect(page.getByTestId("document-type-help")).toHaveText("Guess from the headings; otherwise general.");

    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("results")).toBeVisible();
    expect(sent[0]!.options?.document_type).toBe("auto");
    // A guess names the headings it rested on (review R2), so a wrong guess is easy to see and override.
    await expect(page.getByTestId("profile-line")).toHaveText(`Checked as Research article (from the headings: ${GUESS_EVIDENCE}).`);

    await select.selectOption("commentary");
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]!.options?.document_type).toBe("commentary");
    await expect(page.getByTestId("document-type-help")).toHaveText("An opinion or perspective piece: argued, not reported.");
    // The engine's note stands alone: "Checked as" is never said twice.
    await expect(page.getByTestId("profile-line")).toHaveText(COMMENTARY_NOTE);
    await expect(page.locator("body")).not.toContainText("Checked as Commentary");

    await select.selectOption("grant");
    await expect.poll(() => sent.length).toBe(3);
    await expect(page.getByTestId("profile-line")).toHaveText("Checked as Grant proposal.");

    // Remembered in this browser: the choice, and nothing of the text or the answer.
    await page.reload();
    await expect(page.getByLabel("Check as")).toHaveValue("grant");
    const stored = await page.evaluate(() => ({ keys: Object.keys(localStorage).sort(), values: Object.values(localStorage).join("") }));
    expect(stored.keys).toEqual(["researchly.document-type"]);
    expect(stored.values).not.toContain("Dengue");
    expect(stored.values).not.toContain("causal claim");
  });

  test("without the engine's registry the selector still offers every type", async ({ page }) => {
    await mockEngine(page, undefined, null);
    await page.goto("/");
    const options = page.getByLabel("Check as").locator("option");
    await expect(options).toHaveCount(DOCUMENT_TYPES.length);
    await expect(options.nth(2)).toHaveText("manuscript");
    await expect(page.getByTestId("document-type-help")).toHaveCount(0);
  });

  test("the brief: five questions in order, the evidence quoted in the serif, the frequent checks, the source; never a score", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    expect(sent[0]!.options?.review).toBe(true);

    const tabs = page.getByRole("tablist", { name: "Results view" });
    await expect(tabs.getByRole("tab")).toHaveText(["Suggestions", "Reviewer’s brief", "Narrative map"]);
    await expect(page.getByTestId("view-suggestions")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("brief")).toHaveCount(0);

    await page.getByTestId("view-brief").click();
    await expect(page.getByTestId("view-brief")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("suggestion-card")).toHaveCount(0);
    const brief = page.getByTestId("brief");
    const questions = brief.getByTestId("brief-question");
    await expect(questions).toHaveCount(5);
    for (const [i, q] of REVIEW.questions.entries()) {
      await expect(questions.nth(i)).toHaveAttribute("data-question", q.id);
      await expect(questions.nth(i).locator("h3")).toContainText(q.question);
      await expect(questions.nth(i).locator(".brief-verdict")).toHaveText(q.verdict);
    }
    // Question A is the writer's, as the engine gives it.
    await expect(questions.nth(0)).toContainText("Yours to answer");
    // The evidence is the writer's own sentence, quoted and set in the serif, in an evidence list.
    const evidence = questions.nth(2).locator(".brief-evidence q");
    await expect(evidence).toHaveText("It is clearly proven that vector control reduces transmission.");
    expect(await evidence.evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/Charter|Georgia/);
    await expect(questions.nth(4).locator(".brief-evidence q")).toHaveText("This could potentially suggest seasonal forcing.");
    await expect(questions.nth(1).locator(".brief-evidence")).toHaveCount(0);
    // Then the checks that fired most, in words, and the source set like a card's.
    const rules = brief.getByTestId("brief-rules");
    await expect(rules.locator("li")).toHaveText(["Repeated word 2 times", "Booster overclaims certainty once"]);
    await expect(brief.locator(".brief-source cite")).toHaveText(REVIEW.source);
    await expect(page.locator("body")).not.toContainText(/overall score|grade|\d+ ?\/ ?10/i);
    await expect(page.locator("meter, progress")).toHaveCount(0);

    // Arrow keys move between the tabs; the suggestions come back untouched.
    await page.getByTestId("view-brief").focus();
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByTestId("view-suggestions")).toBeFocused();
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
    await expect(page.getByTestId("brief")).toHaveCount(0);

    // The brief view survives a re-check, and nothing of it is stored.
    await page.getByTestId("view-brief").click();
    await check(page);
    await expect(page.getByTestId("brief-question")).toHaveCount(5);
    expect(sent).toHaveLength(2);
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  });

  test("no brief from the engine, or a check run in Draft, is said in one line", async ({ page }) => {
    let draft = false;
    const sent = await mockEngine(page, (_r, route) => json(route, 200, draft ? { ...happyResponse, mode: "draft", review: null } : { ...happyResponse, review: null }));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("view-brief").click();
    await expect(page.getByTestId("brief-missing")).toContainText("did not return a brief");
    draft = true;
    await check(page);
    const line = page.getByTestId("brief-needs-revise");
    await expect(line).toContainText("needs Revise mode");
    // The website always asks for Revise (review R6); an engine that still ran Draft gets a switch that checks again.
    draft = false;
    await line.getByRole("button", { name: "Switch to Revise" }).click();
    await expect(page.getByTestId("brief-missing")).toBeVisible();
    expect(sent.map((r) => r.options?.mode)).toEqual(["revise", "revise", "revise"]);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`the brief on a phone, ${scheme}: no horizontal scroll, no serious axe violations`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await mockEngine(page);
      await page.goto("/");
      await paste(page, SAMPLE_TEXT);
      await check(page);
      await page.getByLabel("Check as").selectOption("commentary");
      await expect(page.getByTestId("profile-line")).toHaveText(COMMENTARY_NOTE);
      await page.getByTestId("view-brief").click();
      await expect(page.getByTestId("brief-question")).toHaveCount(5);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
      const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
    });
  }
});

test.describe("the narrative map (S4b)", () => {
  test("the third tab: the note, one strip per section with each move's status in words, a missing move's question, lesson and frame, the links, the hedging table", async ({
    page,
  }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    // The map is asked for on every check, with the brief.
    expect(sent[0]!.options?.narrative).toBe(true);
    await expect(page.getByTestId("narrative-map")).toHaveCount(0);

    await page.getByTestId("view-narrative").click();
    await expect(page.getByTestId("view-narrative")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("suggestion-card")).toHaveCount(0);
    await expect(page.getByTestId("brief")).toHaveCount(0);
    const map = page.getByTestId("narrative-map");
    await expect(map.getByTestId("narrative-note")).toHaveText(NARRATIVE.note);

    // One strip per section, in the document's order, each move in the section's expected order.
    const strips = map.getByTestId("narrative-section");
    await expect(strips).toHaveCount(3);
    for (const [i, s] of NARRATIVE.sections.entries()) {
      await expect(strips.nth(i)).toHaveAttribute("data-section", s.section);
      await expect(strips.nth(i).locator("h3")).toContainText(s.label);
      const cells = strips.nth(i).getByTestId("narrative-move");
      await expect(cells).toHaveCount(s.moves.length);
      for (const [j, m] of s.moves.entries()) {
        await expect(cells.nth(j)).toHaveAttribute("data-status", m.status);
        await expect(cells.nth(j)).toContainText(m.label);
      }
    }
    // The status is said in words, not colour alone: a missing cell says "missing", an out-of-order one says so.
    const intro = strips.nth(0);
    await expect(intro.getByTestId("narrative-move").nth(1)).toContainText("missing");
    await expect(intro.getByTestId("narrative-move").nth(0)).not.toContainText("missing");
    const discussion = strips.nth(2);
    await expect(discussion.getByTestId("narrative-move").nth(1)).toContainText("out of order");
    // A hollow dot for a missing move, a filled one for a present move: shape, not colour.
    const dotBg = (cell: import("@playwright/test").Locator) => cell.locator(".nmap-dot").evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(await dotBg(intro.getByTestId("narrative-move").nth(1))).toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
    expect(await dotBg(intro.getByTestId("narrative-move").nth(0))).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);

    // Under the strip, the missing move opens to its question, the lesson and the frame to fill in.
    const gap = NARRATIVE.sections[0]!.moves[1]!;
    const detail = intro.getByTestId("narrative-detail").first();
    await expect(detail).toHaveAttribute("data-move", gap.id);
    await expect(detail.locator(".nmap-question")).toHaveText(gap.question);
    await expect(detail.locator(".nmap-plain")).toHaveText(gap.plain);
    await expect(detail.locator(".nmap-frame-text")).toHaveText(gap.frame);
    await expect(detail.locator(".nmap-frame-caption")).toHaveText("A frame to fill in; the words are yours.");
    expect(await detail.locator(".nmap-frame-text").evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/Charter|Georgia/);
    await expect(detail.locator(".card-source cite")).toHaveText(gap.source);
    // The out-of-order move carries its note.
    await expect(discussion.getByTestId("narrative-detail").nth(1)).toContainText("Appears after what should change.");

    // A present move keeps the writer's own sentence behind a disclosure, in the serif.
    const present = intro.getByTestId("narrative-present").first();
    await expect(present.locator("q")).toBeHidden();
    await present.locator("summary").click();
    await expect(present.locator("q")).toHaveText("Dengue 🦟 remains a major burden across South-East Asia.");
    expect(await present.locator("q").evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/Charter|Georgia/);

    // Then the argument's missing links, the hedging table (every value in text) and the source.
    const links = map.getByTestId("narrative-link");
    await expect(links).toHaveCount(2);
    await expect(links.first()).toContainText("Discussion");
    await expect(links.first()).toContainText(NARRATIVE.missing_links![0]!.message);
    const rows = map.getByTestId("narrative-hedging-row");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(2).locator("th")).toHaveText("Discussion");
    await expect(rows.nth(2).locator("td")).toHaveText(["10.5", "0.0", "heavily hedged"]);
    await expect(map.locator(".nmap-source cite")).toHaveText(NARRATIVE.source);
    await expect(page.locator("meter, progress")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(/overall score|grade|\d+ ?\/ ?10/i);

    // The map view survives a re-check, and nothing of it is stored.
    await check(page);
    await expect(page.getByTestId("narrative-section")).toHaveCount(3);
    expect(sent).toHaveLength(2);
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
    // Arrow keys reach it from the brief and the suggestions come back untouched.
    await page.getByTestId("view-narrative").focus();
    await page.keyboard.press("Home");
    await expect(page.getByTestId("view-suggestions")).toBeFocused();
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
  });

  test("no map from the engine, or a check run in Draft, is said in one line", async ({ page }) => {
    let draft = false;
    await mockEngine(page, (_r, route) =>
      json(route, 200, draft ? { ...happyResponse, mode: "draft", review: null, narrative: null } : { ...happyResponse, narrative: null }),
    );
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("view-narrative").click();
    await expect(page.getByTestId("narrative-missing")).toContainText("did not return a narrative map");
    draft = true;
    await check(page);
    const line = page.getByTestId("narrative-needs-revise");
    await expect(line).toContainText("needs Revise mode");
    await expect(line.getByRole("button", { name: "Switch to Revise" })).toBeVisible();
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`the map on a phone, ${scheme}: the strip wraps, no horizontal scroll, no serious axe violations`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await mockEngine(page);
      await page.goto("/");
      await paste(page, SAMPLE_TEXT);
      await check(page);
      await page.getByTestId("view-narrative").click();
      await expect(page.getByTestId("narrative-section")).toHaveCount(3);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      // The Discussion strip has five cells: on a phone they sit on more than one line.
      const tops = await page.getByTestId("narrative-section").nth(2).getByTestId("narrative-move").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
      expect(new Set(tops).size).toBeGreaterThan(1);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
      const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
    });
  }
});

test.describe("idle state", () => {
  test("the key teaches all four types, with the same non-colour cues as the highlights", async ({ page }) => {
    await page.goto("/");
    const key = page.getByTestId("reading-key");
    await expect(key.getByRole("heading", { name: "How to read the feedback" })).toBeVisible();
    for (const label of ["Correction", "Improvement", "Convention", "Preference"]) await expect(key).toContainText(label);
    const styles: Record<string, string> = { correction: "solid", improvement: "double", convention: "dotted", preference: "dashed" };
    for (const [cat, style] of Object.entries(styles)) {
      expect(await key.locator(`.spec-${cat}`).evaluate((el) => getComputedStyle(el).textDecorationStyle), cat).toBe(style);
    }
    // The specimens shown are the ones the engine's tests verify (reading-key.json).
    for (const [cat, s] of Object.entries(READING_KEY)) await expect(key.locator(`.spec-${cat}`)).toHaveText(s.flagged);
    // A convention is never presented as an error, here either.
    await expect(key.locator(".key-convention")).toContainText("Never an error");
    const conv = await key.locator(".spec-convention").evaluate((el) => {
      const cs = getComputedStyle(el);
      return [cs.textDecorationColor, cs.backgroundColor, getComputedStyle(el.closest("li")!.querySelector(".key-label")!).color];
    });
    for (const c of conv) expect(isReddish(rgb(c)), c).toBe(false);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });

  test("the example fills only an empty editor and sends nothing until Check", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await page.getByTestId("insert-example").click();
    await expect(page.getByLabel("Text to check")).toBeFocused();
    await expect(page.getByLabel("Text to check")).toHaveValue(/Methods\n/);
    // Offered only while the editor is empty, so it can never overwrite a draft.
    await expect(page.getByTestId("insert-example")).toHaveCount(0);
    expect(sent).toHaveLength(0);
    await page.getByLabel("Text to check").fill("");
    await expect(page.getByTestId("insert-example")).toBeVisible();
  });

  test("on a phone the key gives way to the results after a check", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await mockEngine(page);
    await page.goto("/");
    await expect(page.getByTestId("reading-key")).toBeVisible();
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("suggestion-card").first()).toBeVisible();
    await expect(page.getByTestId("reading-key")).toBeHidden();
  });
});

test.describe("health", () => {
  test("a degraded grammar tier shows a calm banner with detail and remedy", async ({ page }) => {
    await mockEngine(page, (_req, route) => json(route, 200, degradedGrammarResponse));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const banner = page.getByTestId("health-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Grammar checks unavailable");
    await expect(banner).toContainText("LanguageTool did not respond in time");
    await expect(banner).toContainText("check again in a minute");
    await expect(banner).not.toContainText("Learned corrections");
    // The rest of the results still render.
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
    const color = await banner.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(isReddish(rgb(color))).toBe(false);
  });
});

test.describe("states and errors", () => {
  test("loading: busy button, text kept, cancellable", async ({ page }) => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    await mockEngine(page, async (req, route) => {
      await gate;
      await json(route, 200, happyResponse);
    });
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const btn = page.getByTestId("check");
    await expect(btn).toHaveAttribute("aria-disabled", "true");
    await expect(btn).toHaveText(/Checking/);
    await expect(page.getByTestId("announcer")).toHaveText(/Checking your text/);
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(btn).toHaveText("Check");
    await expect(page.getByTestId("announcer")).toHaveText(/cancelled/);
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
    release();
  });

  test("empty input is caught client-side with no request", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, "   \n  ");
    await check(page);
    await expect(page.getByTestId("input-problem")).toHaveText(/Paste or type some text/);
    await expect(page.getByLabel("Text to check")).toBeFocused();
    expect(sent).toHaveLength(0);
  });

  test("over-long input is caught client-side with no request", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await page.getByLabel("Text to check").fill("a".repeat(MAX_CONTENT_CHARS + 1));
    await check(page);
    await expect(page.getByTestId("input-problem")).toContainText("1,000,001 characters");
    expect(sent).toHaveLength(0);
  });

  test("an empty result says so, without implying a score", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 200, emptyResponse));
    await page.goto("/");
    await paste(page, "A perfectly ordinary sentence.");
    await check(page);
    await expect(page.getByTestId("empty-state")).toContainText("No suggestions. That’s not a score");
    await expect(page.getByTestId("empty-state")).toContainText("none of our checks fired");
  });

  test("engine unreachable: text kept, Retry works", async ({ page }) => {
    let up = false;
    await mockEngine(page, async (_req, route) => {
      if (!up) await route.abort("connectionrefused");
      else await json(route, 200, happyResponse);
    });
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const err = page.getByTestId("check-error");
    await expect(err).toHaveAttribute("data-kind", "unreachable");
    await expect(err).toContainText("Could not reach the checking engine");
    await expect(err).toContainText(/tried [a-z0-9.:-]+/); // names the engine host it tried
    await expect(err).toBeFocused();
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
    up = true;
    await page.getByTestId("retry").click();
    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();
    await expect(page.getByTestId("check-error")).toHaveCount(0);
  });

  test("413 explains the limit", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 413, error413));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const err = page.getByTestId("check-error");
    await expect(err).toContainText("This text is too long for one check");
    await expect(err).toContainText("1,000,000 characters");
    await expect(page.getByTestId("retry")).toHaveCount(0);
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
  });

  test("429 asks to slow down", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 429, error429, { "retry-after": "20" }));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const err = page.getByTestId("check-error");
    await expect(err).toContainText("Too many checks in a short time");
    await expect(err).toContainText("20 seconds");
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
  });

  test("422 shows the engine's message", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 422, error422));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("check-error")).toContainText("format must be one of");
  });

  test("500 shows the request id to quote", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 500, error500));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const err = page.getByTestId("check-error");
    await expect(err).toContainText("Something went wrong on our side");
    await expect(page.getByTestId("request-id")).toHaveText("req-500-a9f3c2");
    await expect(page.getByTestId("retry")).toBeVisible();
    await expect(page.getByLabel("Text to check")).toHaveValue(SAMPLE_TEXT);
  });
});

test.describe("accessibility", () => {
  test("keyboard only: check, read Why, jump to the text and back", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    const tabTo = async (pred: () => Promise<boolean>, max = 80) => {
      for (let i = 0; i < max; i++) {
        await page.keyboard.press("Tab");
        if (await pred()) return;
      }
      throw new Error("focus target not reached");
    };
    const active = (fn: (el: Element) => boolean) => page.evaluate(`(${fn.toString()})(document.activeElement)`) as Promise<boolean>;

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to the checker" })).toBeFocused();
    await tabTo(() => active((el) => el.tagName === "TEXTAREA"));
    await page.keyboard.insertText(SAMPLE_TEXT);
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Format")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Check as")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Reporting checklist")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Show preferences")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("check")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();
    await expect(page.getByTestId("announcer")).toHaveText(/Check complete\. 8 suggestions/);

    // Into the document region, arrow to the first highlight, Enter opens its card.
    await tabTo(() => active((el) => el.getAttribute("data-testid") === "document"));
    await page.keyboard.press("ArrowDown");
    const firstId = await page.evaluate(() => document.activeElement?.getAttribute("data-sids"));
    expect(firstId).toBeTruthy();
    await page.keyboard.press("Enter");
    await expect(page.locator(`#card-${firstId!.split(" ")[0]}`)).toBeFocused();

    // Tab onwards to the card's Why, open it, then "Show in text".
    await tabTo(() => active((el) => el.tagName === "SUMMARY" && el.textContent === "The full reasoning"));
    await page.keyboard.press("Enter");
    await expect(page.locator("details.why[open]")).toHaveCount(1);
    await tabTo(() => active((el) => el.textContent === "Show in text"));
    await page.keyboard.press("Enter");
    const focusedMark = await page.evaluate(() => document.activeElement?.closest("[data-testid=document]") !== null);
    expect(focusedMark).toBe(true);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`axe: no serious or critical violations on the results view (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockEngine(page, (_r, route) =>
        json(route, 200, { ...withPreferencesResponse, health: degradedGrammarResponse.health }),
      );
      await page.goto("/");
      await paste(page, SAMPLE_TEXT);
      await page.getByLabel("Show preferences").check();
      await check(page);
      await expect(page.getByTestId("suggestion-card")).toHaveCount(10);
      await page.getByTestId("suggestion-card").first().getByText("The full reasoning").click();
      await page.getByTestId("section-filter").selectOption("methods");
      await expect(page.getByTestId("whole-document")).toHaveCount(0);
      await page.getByTestId("check").focus();
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
      const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
    });
  }

  test("axe: error state", async ({ page }) => {
    await mockEngine(page, (_r, route) => json(route, 500, error500));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("check-error")).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });

  for (const width of [375, 360]) {
    test(`mobile ${width}px: no horizontal scroll`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await mockEngine(page);
      await page.goto("/");
      await paste(page, SAMPLE_TEXT + "\nA very long unbroken token: " + "x".repeat(300) + "\nhttps://example.org/" + "a/".repeat(80));
      await check(page);
      await expect(page.getByTestId("suggestion-card").first()).toBeVisible();
      await page.getByTestId("suggestion-card").first().getByText("The full reasoning").click();
      await page.getByTestId("section-filter").selectOption("discussion");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});

test.describe("security", () => {
  test("headers: strict CSP with only self + engine in connect-src", async ({ request }) => {
    const res = await request.get("/");
    const h = res.headers();
    const csp = h["content-security-policy"]!;
    expect(csp).toMatch(/connect-src 'self' http:\/\/127\.0\.0\.1:8099(;|$)/);
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(h["referrer-policy"]).toBe("no-referrer");
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["set-cookie"]).toBeUndefined();
    expect(h["x-powered-by"]).toBeUndefined();
  });

  test("no CSP violations or console errors during a full check", async ({ page }) => {
    const problems: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") problems.push(m.text());
    });
    page.on("pageerror", (e) => problems.push(e.message));
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
    expect(problems).toEqual([]);
  });

  test("the page loads nothing from third parties", async ({ page, baseURL }) => {
    const external: string[] = [];
    page.on("request", (r) => {
      const u = r.url();
      if (!u.startsWith(baseURL!) && !u.startsWith("http://127.0.0.1:8099") && !u.startsWith("data:")) external.push(u);
    });
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("results")).toBeVisible();
    expect(external).toEqual([]);
  });
});

test.describe("print or save as PDF (S4)", () => {
  test("the report exists only on paper: numbered highlights beside the suggestions, then the brief, nothing else", async ({ page }) => {
    // The browser's print dialog cannot open here: record the call instead.
    await page.addInitScript(() => {
      (window as unknown as { __printed: number }).__printed = 0;
      window.print = () => {
        (window as unknown as { __printed: number }).__printed += 1;
      };
    });
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("results")).toBeVisible();
    // Nothing of the report is in the page until it is asked for.
    await expect(page.getByTestId("print-report")).toHaveCount(0);

    await page.getByTestId("print-report-button").click();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __printed: number }).__printed)).toBe(1);

    // On paper: the report, and only the report.
    await page.emulateMedia({ media: "print" });
    const report = page.getByTestId("print-report");
    await expect(report).toBeVisible();
    await expect(page.getByTestId("results")).toBeHidden();
    await expect(page.locator(".site-header")).toBeHidden();
    await expect(page.locator(".site-footer")).toBeHidden();
    const marks = report.getByTestId("print-mark");
    expect(await marks.count()).toBeGreaterThan(0);
    const cards = report.getByTestId("print-card");
    expect(await cards.count()).toBe(happyResponse.suggestions.length);
    // Every number on a highlight is the number of a listed suggestion.
    const refs = (await report.locator(".print-ref").allTextContents()).flatMap((t) => t.split(",").map(Number));
    const listed = (await report.locator(".print-n").allTextContents()).map(Number);
    expect(refs.length).toBeGreaterThan(0);
    for (const n of refs) expect(listed).toContain(n);
    await expect(report.locator(".print-brief [data-question]")).toHaveCount(5);
    // Then the narrative map on its own page: the strips as text rows with every status word, a missing move's frame, the links, the hedging table.
    const narrative = report.getByTestId("print-narrative");
    await expect(narrative).toBeVisible();
    await expect(narrative.getByTestId("narrative-section")).toHaveCount(3);
    await expect(narrative.locator(".nmap-cell-status")).toHaveCount(NARRATIVE.sections.reduce((n, s) => n + s.moves.length, 0));
    await expect(narrative.locator("details")).toHaveCount(0);
    await expect(narrative).toContainText(NARRATIVE.sections[0]!.moves[1]!.frame);
    await expect(narrative.getByTestId("narrative-link")).toHaveCount(2);
    await expect(narrative.getByTestId("narrative-hedging-row")).toHaveCount(3);
    expect(await narrative.evaluate((el) => getComputedStyle(el).breakBefore)).toBe("page");
    await expect(report).toContainText("Nothing was sent anywhere");

    // After printing the report is gone again; the screen is as before.
    await page.emulateMedia({ media: "screen" });
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    await expect(page.getByTestId("print-report")).toHaveCount(0);
    await expect(page.getByTestId("results")).toBeVisible();
  });

  test("the browser's own print command (beforeprint) mounts the report too", async ({ page }) => {
    // A real window.print() in headless Chromium fires afterprint at once, which would unmount it again.
    await page.addInitScript(() => {
      window.print = () => {};
    });
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await expect(page.getByTestId("results")).toBeVisible();
    await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
    await expect(page.getByTestId("print-report")).toHaveCount(1);
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    await expect(page.getByTestId("print-report")).toHaveCount(0);
  });
});

/* ---------- S4c: the Codex review's web fixes, lessons, checklists, dismissal ---------- */

const learn = (id: string) => LEARN_CARDS.find((c) => c.id === id)!;
const axeBad = async (page: import("@playwright/test").Page) => {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`);
};

test.describe("Revise on the website (review R6)", () => {
  test("every check asks for Revise; an engine that still ran Draft says what it held back and checks again in Revise", async ({ page }) => {
    let draft = true;
    const sent = await mockEngine(page, (_req, route) =>
      json(route, 200, draft ? { ...happyResponse, mode: "draft", hidden_by_mode: 3, review: null, narrative: null } : happyResponse),
    );
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const line = page.getByTestId("held-back");
    await expect(line).toContainText("Draft mode held back 3 whole-document suggestions.");
    draft = false;
    await line.getByRole("button", { name: "Check again in Revise" }).click();
    await expect(page.getByTestId("held-back")).toHaveCount(0);
    expect(sent.map((r) => r.options?.mode)).toEqual(["revise", "revise"]);
  });
});

test.describe("the brief's statuses (review R4)", () => {
  test("a small word after each question says what the answer rests on, never a colour; the disclaimer closes the brief before the source", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("view-brief").click();
    const questions = page.getByTestId("brief-question");
    await expect(questions).toHaveCount(5);
    // Question A is the writer's: no status word.
    await expect(questions.nth(0).getByTestId("brief-status")).toHaveCount(0);
    await expect(questions.nth(1).getByTestId("brief-status")).toHaveText("not detected");
    await expect(questions.nth(2).getByTestId("brief-status")).toHaveText("detected");
    await expect(questions.nth(2).locator("h3")).toContainText(`${REVIEW.questions[2]!.question} (detected)`);
    // The same ink for every status: the word carries it, never a colour.
    const colours = await page.getByTestId("brief-status").evaluateAll((els) => els.map((e) => getComputedStyle(e).color));
    expect(new Set(colours).size).toBe(1);
    const disclaimer = page.getByTestId("brief-disclaimer");
    await expect(disclaimer).toHaveText(REVIEW_DISCLAIMER);
    const order = await page.getByTestId("brief").evaluate((el) => {
      const all = Array.from(el.querySelectorAll("*"));
      return [all.indexOf(el.querySelector("[data-testid=brief-rules]")!), all.indexOf(el.querySelector("[data-testid=brief-disclaimer]")!), all.indexOf(el.querySelector(".brief-source")!)];
    });
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });
});

test.describe("the lesson on every card (S4)", () => {
  test("a closed disclosure opens the Learn card in place: title, lesson, before and after, the habit, the source, and All lessons in a new tab", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const card = page.locator(`#card-${byRule("C120").id}`);
    const lesson = card.getByTestId("lesson");
    const want = learn("concise-words");
    await expect(lesson).toHaveAttribute("data-lesson", want.id);
    await expect(lesson).not.toHaveAttribute("open");
    await expect(lesson.locator(".lesson-title")).toBeHidden();
    await lesson.getByText("The lesson").click();
    await expect(lesson.locator(".lesson-title")).toHaveText(want.title);
    await expect(lesson.locator(".lesson-text")).toHaveText(want.lesson);
    await expect(lesson.locator(".lesson-example-label")).toHaveText(["Before", "After"]);
    await expect(lesson.locator(".lesson-quote q")).toHaveText([want.before, want.after]);
    expect(await lesson.locator(".lesson-quote").first().evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/Charter|Georgia/);
    await expect(lesson.locator(".lesson-habit")).toContainText(want.habit);
    await expect(lesson.locator(".lesson-source cite")).toHaveText(want.source);
    const all = lesson.getByRole("link", { name: /All lessons/ });
    await expect(all).toHaveAttribute("href", "/learn");
    await expect(all).toHaveAttribute("target", "_blank");
    await expect(all).toHaveAttribute("rel", "noopener");
    // Reading the lesson neither jumps to the text nor sends anything.
    await lesson.locator(".lesson-text").click();
    await expect(card).not.toHaveClass(/is-active/);
    expect(sent).toHaveLength(1);
    // A suggestion without a known lesson has no disclosure.
    await expect(page.locator(`#card-${byRule("V305").id}`).getByTestId("lesson")).toHaveCount(0);
  });

  test("the narrative map's missing moves and missing links carry their lessons; a link's sentences open on request", async ({ page }) => {
    await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.getByTestId("view-narrative").click();
    const gap = page.getByTestId("narrative-section").nth(0).getByTestId("narrative-detail").first();
    await expect(gap.getByTestId("lesson")).toHaveAttribute("data-lesson", "introduction");
    await gap.getByTestId("lesson").getByText("The lesson").click();
    await expect(gap.locator(".lesson-title")).toHaveText(learn("introduction").title);
    const links = page.getByTestId("narrative-link");
    await expect(links.nth(0).getByTestId("lesson")).toHaveAttribute("data-lesson", "warranting");
    await expect(links.nth(1).getByTestId("lesson")).toHaveCount(0);
    const sentences = links.nth(0).getByTestId("narrative-link-evidence");
    await expect(sentences.locator("q")).toBeHidden();
    await sentences.locator("summary").click();
    await expect(sentences.locator("q")).toHaveText(NARRATIVE.missing_links![0]!.evidence!);
    await expect(links.nth(1).getByTestId("narrative-link-evidence")).toHaveCount(0);
  });
});

test.describe("reporting checklists (S4)", () => {
  test("None by default and not sent; a chosen checklist is sent, remembered, and read in a fourth tab with statuses in words", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    const select = page.getByLabel("Reporting checklist");
    await expect(select).toHaveValue("none");
    await expect(select.locator("option")).toHaveText(["None", "Auto", ...CHECKLISTS.map((c) => c.label)]);
    await expect(page.getByTestId("checklist-help")).toHaveCount(0);
    await paste(page, SAMPLE_TEXT);
    await check(page);
    expect(sent[0]!.options).not.toHaveProperty("checklist");
    await expect(page.getByRole("tablist", { name: "Results view" }).getByRole("tab")).toHaveText(["Suggestions", "Reviewer’s brief", "Narrative map"]);

    // A change checks again, like "Check as"; the design reads under the control.
    await select.selectOption("epiforge");
    await expect(page.getByTestId("checklist-help")).toHaveText("For epidemic forecasts, projections and predictions.");
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]!.options?.checklist).toBe("epiforge");
    const tabs = page.getByRole("tablist", { name: "Results view" }).getByRole("tab");
    await expect(tabs).toHaveText(["Suggestions", "Reviewer’s brief", "Narrative map", "Checklist"]);
    await page.getByTestId("view-checklist").click();
    const view = page.getByTestId("checklist");
    await expect(view.getByTestId("checklist-note")).toHaveText(CHECKLIST.note);
    const items = view.getByTestId("checklist-item");
    await expect(items).toHaveCount(CHECKLIST.items.length);
    for (const [i, it] of CHECKLIST.items.entries()) {
      await expect(items.nth(i)).toHaveAttribute("data-item", it.id);
      await expect(items.nth(i).locator("h3")).toHaveText(it.topic);
      await expect(items.nth(i).locator(".checklist-question")).toHaveText(it.question);
    }
    await expect(items.nth(0).getByTestId("checklist-status")).toContainText("reported");
    await expect(items.nth(0).locator(".checklist-evidence q")).toHaveText(CHECKLIST.items[0]!.evidence!);
    await expect(items.nth(1).getByTestId("checklist-status")).toContainText("needs your check");
    await expect(items.nth(1).locator(".checklist-plain")).toHaveText(CHECKLIST.items[1]!.plain);
    // Statuses are words: the same ink whatever the status.
    const inks = await view.locator(".checklist-status-word").evaluateAll((els) => els.map((e) => getComputedStyle(e).color));
    expect(new Set(inks).size).toBe(1);
    await expect(view.locator(".checklist-source cite")).toHaveText(CHECKLIST.source);
    await expect(view.getByTestId("checklist-scope")).toHaveText("This checks reporting only, never the science.");

    // "Not applicable": the writer's call, this session only.
    const na = items.nth(1).getByTestId("checklist-na");
    await expect(na).toHaveAttribute("aria-pressed", "false");
    await na.click();
    await expect(na).toHaveAttribute("aria-pressed", "true");
    await expect(items.nth(1).getByTestId("checklist-status")).toHaveText("not applicable (your call)");
    expect(sent).toHaveLength(2);

    // Remembered in this browser: the checklist's id, nothing else of the check.
    const stored = await page.evaluate(() => ({ keys: Object.keys(localStorage).sort(), values: Object.values(localStorage).join("") }));
    expect(stored.keys).toEqual(["researchly.checklist"]);
    expect(stored.values).toBe("epiforge");
    await page.reload();
    await expect(page.getByLabel("Reporting checklist")).toHaveValue("epiforge");
  });

  test("with none chosen, the checklist the text's words point to is offered in one quiet line, and taking it checks again", async ({ page }) => {
    const sent = await mockEngine(page, (req, route) =>
      json(route, 200, req.options?.checklist ? { ...happyResponse, checklist: CHECKLIST } : { ...happyResponse, suggested_checklist: "epiforge" }),
    );
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const offer = page.getByTestId("checklist-offer");
    await expect(offer).toContainText("This reads like an epidemic forecast. Check it against EPIFORGE?");
    await offer.getByRole("button", { name: "Check against EPIFORGE" }).click();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]!.options?.checklist).toBe("epiforge");
    await expect(page.getByLabel("Reporting checklist")).toHaveValue("epiforge");
    await expect(page.getByTestId("view-checklist")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("checklist-item")).toHaveCount(CHECKLIST.items.length);
    await expect(page.getByTestId("checklist-offer")).toHaveCount(0);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`the checklist on a phone, ${scheme}: four tabs wrap, no horizontal scroll, no serious axe violations`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await mockEngine(page);
      await page.goto("/");
      await page.getByLabel("Reporting checklist").selectOption("auto");
      await paste(page, SAMPLE_TEXT);
      await check(page);
      await page.getByTestId("view-checklist").click();
      await expect(page.getByTestId("checklist-item")).toHaveCount(CHECKLIST.items.length);
      await page.getByTestId("checklist-item").nth(2).getByTestId("checklist-na").click();
      const tops = await page.getByRole("tab").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
      expect(new Set(tops).size).toBeGreaterThan(1);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      expect(await axeBad(page)).toEqual([]);
    });
  }
});

test.describe("dismiss once, undo (review proposal 2)", () => {
  test("Not an issue here hides one suggestion for this check only, says so politely with Undo, and Show brings them back", async ({ page }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    const target = page.locator(`#card-${byRule("C120").id}`);
    await target.getByRole("button", { name: "Not an issue here" }).click();
    await expect(target).toHaveCount(0);
    await expect(mark(page, byRule("C120").id)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "7 suggestions" })).toBeVisible();
    await expect(page.getByTestId("dismissed-line")).toHaveText("1 dismissed · Show");
    const live = page.getByTestId("dismiss-live");
    await expect(live).toHaveAttribute("aria-live", "polite");
    await expect(live).toHaveText("Dismissed. Undo");
    // Focus lands on Undo, one key away; Undo brings the card back and focuses it.
    await expect(page.getByTestId("undo-dismiss")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(`#card-${byRule("C120").id}`)).toBeFocused();
    await expect(page.getByRole("heading", { name: "8 suggestions" })).toBeVisible();
    await expect(page.getByTestId("dismissed-line")).toHaveCount(0);

    // Two dismissed, then "Show" restores both.
    await page.locator(`#card-${byRule("C201").id}`).getByTestId("dismiss").click();
    await page.locator(`#card-${byRule("S010").id}`).getByTestId("dismiss").click();
    await expect(page.getByTestId("suggestion-card")).toHaveCount(6);
    await expect(page.getByTestId("filter-all")).toContainText("6");
    await page.getByTestId("show-dismissed").click();
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
    await expect(live).toContainText("2 suggestions shown again.");

    // Nothing was sent or stored for any of it; a new check starts clean.
    expect(sent).toHaveLength(1);
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
    await page.locator(`#card-${byRule("C201").id}`).getByTestId("dismiss").click();
    await check(page);
    await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
    await expect(page.getByTestId("dismissed-line")).toHaveCount(0);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`a dismissed card and an open lesson stay clean under axe (${scheme}), with no horizontal scroll on a phone`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await mockEngine(page);
      await page.goto("/");
      await paste(page, SAMPLE_TEXT);
      await check(page);
      await page.locator(`#card-${byRule("C201").id}`).getByTestId("dismiss").click();
      await expect(page.getByTestId("undo-dismiss")).toBeVisible();
      const card = page.locator(`#card-${byRule("C120").id}`);
      await card.getByTestId("lesson").getByText("The lesson").click();
      await expect(card.locator(".lesson-title")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      expect(await axeBad(page)).toEqual([]);
    });
  }
});

test.describe("the printed report's context (review R8)", () => {
  test("the header says when it was checked and printed, the mode, the guess and its headings, what was unavailable or skipped, what was dismissed, and that the editor has changed", async ({ page }) => {
    await page.addInitScript(() => {
      window.print = () => {};
    });
    await mockEngine(page, (req, route) =>
      json(route, 200, {
        ...happyResponse,
        health: degradedGrammarResponse.health,
        warnings: ["A table could not be read and was skipped."],
        profile: { ...happyResponse.profile, evidence: GUESS_EVIDENCE },
        checklist: req.options?.checklist ? CHECKLIST : null,
      }),
    );
    await page.goto("/");
    await page.getByLabel("Reporting checklist").selectOption("epiforge");
    await paste(page, SAMPLE_TEXT);
    await check(page);
    await page.locator(`#card-${byRule("C120").id}`).getByTestId("dismiss").click();
    await page.getByLabel("Text to check").fill(SAMPLE_TEXT + "\nOne more sentence.");
    await expect(page.getByTestId("stale-note")).toBeVisible();
    await page.getByTestId("view-checklist").click();
    await page.getByTestId("checklist-item").nth(1).getByTestId("checklist-na").click();
    await page.getByTestId("print-report-button").click();
    await page.emulateMedia({ media: "print" });
    const report = page.getByTestId("print-report");
    await expect(report).toBeVisible();
    await expect(report.getByTestId("print-times")).toHaveText(/^Checked \d{1,2} \w+ \d{4}(,| at) \d{2}:\d{2} · Printed \d{1,2} \w+ \d{4}(,| at) \d{2}:\d{2}$/);
    const head = report.locator("header");
    await expect(head).toContainText("Revise mode");
    await expect(head).toContainText(`Checked as Research article (from the headings: ${GUESS_EVIDENCE}).`);
    await expect(report.getByTestId("print-unavailable")).toHaveText("Not available for this check: Grammar, Learned corrections.");
    await expect(report.getByTestId("print-warnings")).toContainText("A table could not be read and was skipped.");
    await expect(report.getByTestId("print-dismissed")).toHaveText("1 suggestion dismissed on screen is left out of this report.");
    await expect(report.getByTestId("print-stale")).toHaveText("This report describes the version that was checked, not the text now in the editor.");
    await expect(report.getByTestId("print-card")).toHaveCount(happyResponse.suggestions.length - 1);
    // The checklist after the narrative map, on its own page, statuses in words, no controls.
    const list = report.getByTestId("print-checklist");
    await expect(list).toBeVisible();
    expect(await list.evaluate((el) => getComputedStyle(el).breakBefore)).toBe("page");
    await expect(list.getByTestId("checklist-item")).toHaveCount(CHECKLIST.items.length);
    await expect(list.getByTestId("checklist-status").nth(0)).toContainText("reported");
    await expect(list.getByTestId("checklist-status").nth(1)).toHaveText("not applicable (your call)");
    await expect(list.getByRole("button")).toHaveCount(0);
    await expect(list).toContainText("This checks reporting only, never the science.");
    await page.emulateMedia({ media: "screen" });
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
  });
});

test.describe("the demo manuscript", () => {
  test("loads the synthetic paper from this site into an empty editor as Markdown, sends nothing, and offers the Word and Overleaf versions", async ({ page, request }) => {
    const sent = await mockEngine(page);
    await page.goto("/");
    const row = page.getByTestId("demo-row");
    await expect(row).toBeVisible();
    await expect(row.getByTestId("demo-docx")).toHaveAttribute("href", "/demo/researchly-demo.docx");
    await expect(row.getByTestId("demo-zip")).toHaveAttribute("href", "/demo/researchly-demo-overleaf.zip");
    for (const path of ["/demo/researchly-demo.docx", "/demo/researchly-demo-overleaf.zip", "/demo/researchly-demo.md"]) {
      expect((await request.get(path)).status(), path).toBe(200);
    }
    await page.getByRole("button", { name: "Try the demo manuscript" }).click();
    await expect(page.getByLabel("Text to check")).toHaveValue(/^# A compartmental model/);
    await expect(page.getByLabel("Text to check")).toBeFocused();
    await expect(page.getByLabel("Format")).toHaveValue("markdown");
    // Offered only while the editor is empty; nothing was checked, and the format choice was not stored.
    await expect(page.getByTestId("demo-row")).toHaveCount(0);
    expect(sent).toHaveLength(0);
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
    await check(page);
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]!.format).toBe("markdown");
    expect(sent[0]!.content.startsWith("# A compartmental model")).toBe(true);
  });
});

test("a demo that cannot be loaded is said under the button, and the editor stays empty", async ({ page }) => {
  const sent = await mockEngine(page);
  await page.route("**/demo/researchly-demo.md", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("/");
  await page.getByTestId("load-demo").click();
  await expect(page.getByTestId("demo-problem")).toHaveText("The demo manuscript could not be loaded. Check your connection and try again.");
  await expect(page.getByLabel("Text to check")).toHaveValue("");
  expect(sent).toHaveLength(0);
});
