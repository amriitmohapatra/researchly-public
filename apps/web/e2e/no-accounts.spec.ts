/**
 * The S1 build (no Supabase config) has no trace of accounts: no sign-in UI,
 * no upload, no settings page, no Supabase code loaded or contacted.
 * Runs in the "chromium" project (playwright.config.ts).
 */
import { expect, test } from "@playwright/test";
import { happyResponse, SAMPLE_TEXT } from "./fixtures";
import { check, json, mockEngine, paste } from "./helpers";

test("without Supabase config there is no sign-in, upload or settings page", async ({ page, baseURL }) => {
  const sent = await mockEngine(page);
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  await page.goto("/");
  await paste(page, SAMPLE_TEXT);
  await check(page);
  await expect(page.getByTestId("results")).toBeVisible();
  expect(sent[0]).not.toHaveProperty("authorization");

  await expect(page.getByRole("button", { name: /sign in/i })).toHaveCount(0);
  await expect(page.getByTestId("upload-row")).toHaveCount(0);
  await expect(page.getByTestId("file-input")).toHaveCount(0);
  await expect(page.getByTestId("mute-rule")).toHaveCount(0);
  expect(requests.filter((u) => u.includes("supabase"))).toEqual([]);
  // supabase-js is loaded on demand only: no script this page loaded contains it.
  const scripts = await page.evaluate(() =>
    performance
      .getEntriesByType("resource")
      .map((e) => e.name)
      .filter((u) => u.endsWith(".js")),
  );
  expect(scripts.length).toBeGreaterThan(0);
  for (const url of scripts) {
    const body = await (await page.request.get(url)).text();
    expect(body, url).not.toContain("/auth/v1");
  }

  const res = await page.goto(`${baseURL}/settings`);
  expect(res?.status()).toBe(404);
});

test("what was approximated while reading pasted text is shown quietly", async ({ page }) => {
  await mockEngine(page, (_r, route) =>
    json(route, 200, { ...happyResponse, warnings: ["The LaTeX could not be fully parsed; it was read with a simpler method."] }),
  );
  await page.goto("/");
  await paste(page, SAMPLE_TEXT);
  await check(page);
  const note = page.getByTestId("read-warnings");
  await expect(note).toContainText("Read with approximations");
  await expect(note).toContainText("read with a simpler method");
  await expect(page.getByTestId("suggestion-card")).toHaveCount(8);
});
