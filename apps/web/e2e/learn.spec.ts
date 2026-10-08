/**
 * S4c: the Learn pages (/learn, /learn/<id>), on the build without accounts.
 * Static pages from the contract's LEARN_CARDS: no engine call, readable
 * without JavaScript, at 375px, axe clean in light and dark.
 */
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { LEARN_CARDS } from "@researchly/contract";
import { ENGINE } from "./fixtures";

const GROUPS = ["Sentences", "Words", "Claims and evidence", "Figures, tables and numbers", "Structure and argument", "Mechanics"];

async function axeSerious(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
  return r.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`);
}

const noOverflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test.describe("Lessons", () => {
  test("the index lists every card under its group, in order, each linking to its page; the header links here", async ({ page }) => {
    const engine: string[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith(ENGINE)) engine.push(r.url());
    });
    await page.goto("/");
    await page.getByTestId("nav-lessons").click();
    await expect(page).toHaveURL(/\/learn$/);
    await expect(page.getByRole("heading", { level: 1, name: "Lessons" })).toBeVisible();
    await expect(page.getByTestId("lesson-group").locator("h2")).toHaveText(GROUPS);
    const links = page.getByTestId("lesson-item").locator("a");
    await expect(links).toHaveCount(LEARN_CARDS.length);
    const hrefs = await links.evaluateAll((els) => els.map((e) => e.getAttribute("href")));
    expect(new Set(hrefs)).toEqual(new Set(LEARN_CARDS.map((c) => `/learn/${c.id}`)));
    const first = LEARN_CARDS[0]!;
    await expect(page.getByTestId("lesson-item").first()).toContainText(first.title);
    await expect(page.getByTestId("lesson-item").first()).toContainText(first.summary);

    await links.first().click();
    await expect(page).toHaveURL(`/learn/${first.id}`);
    await expect(page.getByRole("heading", { level: 1, name: first.title })).toBeVisible();
    // The Learn pages never call the engine (the checker page may ask for its registry; this one doesn't).
    expect(engine.filter((u) => !u.endsWith("/v1/rules"))).toEqual([]);
  });

  test("a lesson: the title, the lesson, Before and After quoted, the habit, the source, and a way back", async ({ page }) => {
    const card = LEARN_CARDS.find((c) => c.id === "hedging") ?? LEARN_CARDS[0]!;
    await page.goto(`/learn/${card.id}`);
    const lesson = page.getByTestId("lesson");
    await expect(lesson.getByRole("heading", { level: 1 })).toHaveText(card.title);
    await expect(page.getByTestId("lesson-text")).toHaveText(card.lesson);
    await expect(page.getByTestId("lesson-before").locator("figcaption")).toHaveText("Before");
    await expect(page.getByTestId("lesson-before").locator("blockquote")).toHaveText(card.before);
    await expect(page.getByTestId("lesson-after").locator("figcaption")).toHaveText("After");
    await expect(page.getByTestId("lesson-after").locator("blockquote")).toHaveText(card.after);
    await expect(page.getByTestId("lesson-habit").getByRole("heading")).toHaveText("Check your own draft");
    await expect(page.getByTestId("lesson-habit")).toContainText(card.habit);
    await expect(page.getByTestId("lesson-source")).toHaveText(`Source: ${card.source}`);
    // Writing is in the serif, the coach in the sans.
    const fonts = await page.evaluate(() => ({
      quote: getComputedStyle(document.querySelector(".lesson-quote")!).fontFamily,
      lesson: getComputedStyle(document.querySelector(".lesson-text")!).fontFamily,
    }));
    expect(fonts.quote).toMatch(/Georgia|serif/);
    expect(fonts.lesson).not.toMatch(/Georgia/);
    await page.getByRole("link", { name: "All lessons" }).click();
    await expect(page).toHaveURL(/\/learn$/);
  });

  test("an unknown lesson is a 404", async ({ request }) => {
    const res = await request.get("/learn/no-such-lesson");
    expect(res.status()).toBe(404);
  });

  test("readable without JavaScript", async ({ browser }) => {
    const ctx = await browser.newContext({ javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto("/learn");
    await expect(page.getByTestId("lesson-item")).toHaveCount(LEARN_CARDS.length);
    await page.goto(`/learn/${LEARN_CARDS[1]!.id}`);
    await expect(page.getByTestId("lesson-habit")).toContainText(LEARN_CARDS[1]!.habit);
    await ctx.close();
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`375px, ${scheme}: no horizontal scroll and no serious axe violations on the index and a lesson`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 800 });
      await page.goto("/learn");
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      expect(await axeSerious(page)).toEqual([]);
      // The longest lesson text on the narrowest screen.
      const longest = [...LEARN_CARDS].sort((a, b) => b.before.length + b.after.length - (a.before.length + a.after.length))[0]!;
      await page.goto(`/learn/${longest.id}`);
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      expect(await axeSerious(page)).toEqual([]);
      const size = await page.evaluate(() => parseFloat(getComputedStyle(document.querySelector(".lesson-text")!).fontSize));
      expect(size).toBeGreaterThanOrEqual(16);
    });
  }
});
