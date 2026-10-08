/**
 * Design review screenshots (not assertions). Runs only with SCREENSHOTS=1:
 *   SCREENSHOTS=1 SHOTS_DIR=/some/dir npx playwright test e2e/screenshots.spec.ts
 */
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { degradedGrammarResponse, withPreferencesResponse, happyResponse, SAMPLE_TEXT } from "./fixtures";
import { json, mockEngine, paste } from "./helpers";
import { ENGINE } from "./fixtures";
import { DEGRADED, fakeOffice, mockWordEngine } from "./word-fixtures";

const DIR = process.env.SHOTS_DIR ?? "test-results/shots";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to capture design screenshots");

for (const scheme of ["light", "dark"] as const) {
  test(`desktop results (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1366, height: 1000 });
    await mockEngine(page, (_r, route) => json(route, 200, { ...happyResponse, health: degradedGrammarResponse.health }));
    await page.goto("/");
    await paste(page, SAMPLE_TEXT);
    await page.getByTestId("check").click();
    await expect(page.getByTestId("suggestion-card").first()).toBeVisible();
    const card = page.getByTestId("suggestion-card").nth(1);
    await card.getByText("The full reasoning").click();
    await card.getByRole("button", { name: "Show in text" }).click();
    await page.screenshot({ path: `${DIR}/desktop-${scheme}.png`, fullPage: true });
    const axe = await new AxeBuilder({ page }).analyze();
    console.log(scheme, "axe violations (all impacts):", axe.violations.map((v) => `${v.id}/${v.impact}`).join(", ") || "none");
  });
}

test("desktop idle", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto("/");
  await page.screenshot({ path: `${DIR}/desktop-idle-light.png`, fullPage: true });
});

test("mobile 375 results", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 375, height: 812 });
  await mockEngine(page, (_r, route) => json(route, 200, withPreferencesResponse));
  await page.goto("/");
  await paste(page, SAMPLE_TEXT);
  await page.getByLabel("Show preferences").check();
  await page.getByTestId("check").click();
  await expect(page.getByTestId("suggestion-card").first()).toBeVisible();
  await page.getByTestId("suggestion-card").first().getByText("The full reasoning").click();
  await page.screenshot({ path: `${DIR}/mobile-375.png`, fullPage: true });
  await page.screenshot({ path: `${DIR}/mobile-375-viewport.png` });
});

test("mobile 375 idle", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.screenshot({ path: `${DIR}/mobile-375-idle.png`, fullPage: true });
});

for (const scheme of ["light", "dark"] as const) {
  test(`word taskpane 360 (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await page.setViewportSize({ width: 360, height: 900 });
    await fakeOffice(page);
    await mockWordEngine(page, ENGINE, { health: DEGRADED });
    await page.goto("/word");
    await page.screenshot({ path: `${DIR}/word-idle-${scheme}.png`, fullPage: true });
    await page.getByTestId("mode-draft").check();
    await page.getByTestId("check-document").click();
    await expect(page.getByTestId("word-card").first()).toBeVisible();
    await page.getByTestId("word-card").first().getByTestId("apply-fix").click();
    await page.getByTestId("word-card").nth(3).getByTestId("select-in-document").click();
    await page.getByTestId("tp-settings").locator("summary").click();
    await page.screenshot({ path: `${DIR}/word-results-${scheme}.png`, fullPage: true });
  });
}
