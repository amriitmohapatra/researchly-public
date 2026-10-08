/**
 * S4c: opt-in progress (project "accounts"). The Settings switch (off by
 * default), recording after a signed-in Word check (counts only, never
 * text, only when switched on), the /progress page's small multiples, the
 * deletes, and the navigation links. Supabase and the engine are mocked.
 */
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { RuleInfo } from "@researchly/contract";
import { mockEngineAuth, mockSupabase, reply, seedSession, USER, type SupabaseState } from "./supabase-mock";
import { DOC, fakeOffice, LOCAL_ENGINE, mockWordEngine, reviseResponse } from "./word-fixtures";

const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"];

async function axeSerious(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  return r.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`);
}

const HELP =
  "Records how many times each check fired and how many words were checked, after each check. Never your text. Off by default; switching it off stops recording.";

const rule = (id: string, short: string, learn_ref: string | null = null): RuleInfo => ({
  id,
  name: id.toLowerCase(),
  short,
  why: "w",
  plain: "p",
  source: "s",
  category: "improvement",
  tier: "craft",
  fix_safety: "review",
  scope: "sentence",
  learn_ref,
});

const REGISTRY = [rule("G106", "Long sentence", "long-sentences"), rule("S001", "Possible misspelling"), rule("W202", "Wordy phrase")];

/** Three recorded checks, oldest first: long sentences fall, misspellings hold, W202 fired once (not shown). */
const RECORDED: SupabaseState["progress"] = [
  { created_at: "2026-10-01T09:00:00Z", words: 500, document_type: "manuscript", counts: { G106: 4, S001: 1 } },
  { created_at: "2026-10-03T09:00:00Z", words: 1000, document_type: "manuscript", counts: { G106: 3, S001: 1, W202: 1 } },
  { created_at: "2026-10-05T09:00:00Z", words: 2000, document_type: "manuscript", counts: { G106: 2, S001: 2 } },
];

const settingsWith = (keep: boolean) => ({ disabled_rules: [], show_preferences: false, locale: "en-GB", keep_progress: keep });

test.describe("Keep my progress (Settings)", () => {
  test("off by default, with its help text; switching on and off saves; Delete my progress asks first", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, { progress: [...RECORDED] });
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse), REGISTRY);
    await page.goto("/settings");
    const sw = page.getByTestId("keep-progress-switch");
    await expect(sw).not.toBeChecked();
    await expect(page.getByTestId("keep-progress-help")).toHaveText(HELP);
    await expect(sw).toHaveAccessibleDescription(HELP);

    await sw.check();
    await expect(page.getByTestId("settings-status")).toHaveText("Your progress will be recorded after each check.");
    expect(sb.settings?.keep_progress).toBe(true);
    const upserts = sb.sent.filter((r) => r.path === "/rest/v1/user_settings" && r.method === "POST");
    expect(JSON.parse(upserts.at(-1)!.body)).toEqual({ keep_progress: true });

    await sw.uncheck();
    await expect(page.getByTestId("settings-status")).toHaveText("Progress is no longer recorded. What was recorded stays until you delete it.");
    expect(sb.settings?.keep_progress).toBe(false);

    await page.getByTestId("delete-progress-open").click();
    const dialog = page.getByTestId("delete-progress-dialog");
    await expect(dialog.getByRole("button", { name: "Keep it" })).toBeFocused();
    expect(await axeSerious(page)).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect(sb.progress).toHaveLength(3);
    await page.getByTestId("delete-progress-open").click();
    await page.getByTestId("delete-progress-confirm").click();
    await expect(page.getByTestId("settings-status")).toHaveText("Your recorded progress was deleted.");
    expect(sb.progress).toEqual([]);
    const del = sb.sent.find((r) => r.method === "DELETE" && r.path === "/rest/v1/progress_events")!;
    expect(del.search).toContain(`user_id=eq.${USER.id}`);
  });

  test("a failed save moves the switch back and says why", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse), REGISTRY);
    await page.route("https://researchlye2e.supabase.co/rest/v1/user_settings*", (route) =>
      route.request().method() === "POST" ? reply(route, 500, { code: "XX000", message: "boom" }) : reply(route, 200, []),
    );
    await page.goto("/settings");
    await page.getByTestId("keep-progress-switch").check();
    await expect(page.getByTestId("settings-error")).toBeVisible();
    await expect(page.getByTestId("keep-progress-switch")).not.toBeChecked();
  });
});

test.describe("recording after a signed-in Word check", () => {
  const withWords = { ...reviseResponse, signed_in: true, metrics: { words: 800 } };

  test("switched on: one row of rule counts, words and the article type, never text", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, { settings: settingsWith(true) });
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, withWords));
    await page.goto("/word");
    await page.getByTestId("check-document").click();
    await expect(page.getByTestId("tp-results")).toBeVisible();
    await expect.poll(() => sb.progress.length).toBe(1);
    const post = sb.sent.find((r) => r.method === "POST" && r.path === "/rest/v1/progress_events")!;
    const row = JSON.parse(post.body);
    expect(row).toEqual({
      words: 800,
      document_type: "manuscript",
      counts: { C120: 1, S010: 3, S001: 1, G106: 1, C201: 1, W211: 1 },
    });
    for (const p of DOC) if (p.text.length > 12) expect(post.body).not.toContain(p.text.slice(0, 12));
    expect(post.body).not.toContain("user_id");
  });

  test("switched off: nothing is sent; a local check is never recorded either", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, { settings: settingsWith(false) });
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, withWords));
    await page.goto("/word");
    await page.getByTestId("check-document").click();
    await expect(page.getByTestId("tp-results")).toBeVisible();
    // The opt-in is read after the check; give the fire-and-forget a moment, then confirm nothing was written.
    await expect.poll(() => sb.sent.filter((r) => r.path === "/rest/v1/user_settings" && r.search.includes("keep_progress")).length).toBeGreaterThan(0);
    expect(sb.sent.filter((r) => r.path === "/rest/v1/progress_events")).toEqual([]);

    sb.settings = settingsWith(true);
    await mockWordEngine(page, LOCAL_ENGINE);
    await page.getByTestId("tp-settings").locator("summary").click();
    await page.getByTestId("engine-local").check();
    await page.getByTestId("check-document").click();
    await expect(page.getByTestId("privacy-line")).toContainText("Nothing is sent over the network");
    await expect(page.getByTestId("tp-results")).toBeVisible();
    expect(sb.sent.filter((r) => r.path === "/rest/v1/progress_events")).toEqual([]);
  });
});

test.describe("the progress page", () => {
  test("signed out: a sign-in prompt", async ({ page }) => {
    await mockSupabase(page);
    await page.goto("/progress");
    await expect(page.getByTestId("progress-signed-out")).toContainText("Sign in to see your progress");
    expect(await axeSerious(page)).toEqual([]);
  });

  test("not opted in: says so and links to Settings", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page, { settings: settingsWith(false) });
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse), REGISTRY);
    await page.goto("/progress");
    const off = page.getByTestId("progress-off");
    await expect(off).toContainText("Researchly records nothing about your checks unless you ask it to");
    await off.getByRole("link", { name: "Settings" }).click();
    await expect(page).toHaveURL(/\/settings$/);
  });

  test("opted in: one small line per rule that fired twice or more, first and latest values in words, a lesson link; no score", async ({
    page,
  }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, { settings: settingsWith(true), progress: [...RECORDED] });
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse), REGISTRY);
    await page.goto("/progress");
    const rows = page.getByTestId("trend");
    await expect(rows).toHaveCount(2);
    // Most often first; W202 fired once and is not shown.
    await expect(rows.nth(0)).toHaveAttribute("data-rule", "G106");
    await expect(rows.nth(0).locator(".trend-name")).toHaveText("Long sentence");
    await expect(rows.nth(0).getByTestId("trend-values")).toHaveText("From 8 to 1 per 1,000 words: fewer.");
    await expect(rows.nth(1).getByTestId("trend-values")).toHaveText("From 2 to 1 per 1,000 words: fewer.");
    await expect(rows.nth(0).getByTestId("sparkline")).toHaveAttribute("aria-label", "Long sentence: from 8 to 1 per 1,000 words, fewer.");
    await expect(rows.nth(0).getByTestId("sparkline").locator("circle.spark-hit")).toHaveCount(3);
    await expect(rows.nth(0).locator(".trend-lesson")).toHaveText("Lesson: One idea per sentence");
    await rows.nth(0).getByRole("link", { name: "One idea per sentence" }).click();
    await expect(page).toHaveURL(/\/learn\/long-sentences$/);
    await page.goBack();
    await expect(page.getByTestId("trend")).toHaveCount(2);
    // Every value is reachable without hovering.
    await page.getByTestId("progress-table").locator("summary").click();
    await expect(page.getByTestId("progress-table").locator("tbody tr").first()).toContainText("8, 3, 1");
    // Never a score, a grade or a total.
    await expect(page.locator("meter, progress")).toHaveCount(0);
    await expect(page.getByTestId("progress")).toContainText("not a score");
    await expect(page.getByTestId("progress")).not.toContainText(/\bgrade\b|\btotal\b|%/i);
    expect(await axeSerious(page)).toEqual([]);

    await page.getByTestId("delete-progress-open").click();
    await page.getByTestId("delete-progress-confirm").click();
    await expect(page.getByTestId("progress-status")).toHaveText("Your recorded progress was deleted.");
    await expect(page.getByTestId("progress-empty")).toBeVisible();
    expect(sb.progress).toEqual([]);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`375px, ${scheme}: progress and settings fit and are axe clean`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await seedSession(page);
      await mockSupabase(page, { settings: settingsWith(true), progress: [...RECORDED] });
      await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse), REGISTRY);
      await page.goto("/progress");
      await expect(page.getByTestId("trend")).toHaveCount(2);
      const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(await overflow()).toBeLessThanOrEqual(0);
      expect(await axeSerious(page)).toEqual([]);
      await page.goto("/settings");
      await expect(page.getByTestId("keep-progress-switch")).toBeChecked();
      expect(await overflow()).toBeLessThanOrEqual(0);
      expect(await axeSerious(page)).toEqual([]);
    });
  }
});

test.describe("navigation", () => {
  test("Lessons always; Progress and Label in the account menu when signed in", async ({ page }) => {
    await mockSupabase(page);
    await page.goto("/");
    await expect(page.getByTestId("nav-lessons")).toBeVisible();
    await expect(page.getByTestId("nav-progress")).toHaveCount(0);

    await seedSession(page);
    await page.goto("/settings");
    await page.getByTestId("account-button").click();
    await expect(page.getByTestId("nav-progress")).toBeVisible();
    await page.getByTestId("nav-label").click();
    await expect(page).toHaveURL(/\/label$/);
    await expect(page.getByRole("heading", { level: 1, name: "Label flags" })).toBeVisible();
    await page.getByTestId("account-button").click();
    await page.getByTestId("nav-progress").click();
    await expect(page).toHaveURL(/\/progress$/);
  });
});
