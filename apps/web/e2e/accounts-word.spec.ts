/**
 * S3: the Word taskpane with accounts (project "accounts"): sign-in by an
 * emailed code inside the pane, account actions on cards, Draft/Revise
 * saved to the account, and no token ever sent to the local engine.
 */
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockEngineAuth, mockSupabase, reply, seedSession, USER } from "./supabase-mock";
import { draftResponse, fakeOffice, LOCAL_ENGINE, mockWordEngine, reviseResponse } from "./word-fixtures";

const tokenLabel = (h: string | undefined) => h?.match(/\.sig-([a-z]+)$/)?.[1];

function card(page: Page, text: string) {
  return page.getByTestId("word-card").filter({ hasText: text });
}

async function check(page: Page) {
  await page.getByTestId("check-document").click();
  await expect(page.getByTestId("tp-results")).toBeVisible();
}

test.describe("Word taskpane, signed out (accounts configured)", () => {
  test("cards carry no account actions, and no token is sent", async ({ page }) => {
    await mockSupabase(page);
    await fakeOffice(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    await page.goto("/word");
    await expect(page.getByTestId("tp-sign-in")).toBeVisible();
    await check(page);
    expect(calls.filter((c) => c.path === "/v1/analyze-word")[0]!.authorization).toBeUndefined();
    await expect(page.getByTestId("mute-rule")).toHaveCount(0);
    await expect(page.getByTestId("add-word")).toHaveCount(0);
    await page.getByTestId("tp-settings").locator("summary").click();
    await expect(page.getByTestId("tp-settings")).toContainText("Sign in to mute rules");
  });

  test("sign_in_required (too long without an account) is shown with a Sign in button", async ({ page }) => {
    await mockSupabase(page);
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) =>
      reply(route, 401, {
        error: {
          code: "sign_in_required",
          message: "Without an account Researchly checks up to 1,500 words at a time. Sign in to check a whole chapter.",
          request_id: "req-401-w",
        },
      }),
    );
    await page.goto("/word");
    await page.getByTestId("check-document").click();
    await expect(page.getByTestId("tp-error")).toContainText("checks up to 1,500 words at a time");
    await page.getByTestId("tp-error-sign-in").click();
    await expect(page.getByTestId("code-sign-in")).toBeVisible();
  });

  test("sign in with an emailed code, inside the pane; a wrong code is explained", async ({ page }) => {
    const sb = await mockSupabase(page);
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    await page.goto("/word");
    await page.getByTestId("tp-sign-in").click();
    await expect(page.getByTestId("code-email")).toBeFocused();
    await page.getByTestId("code-email").fill(USER.email);
    await page.getByTestId("code-send").click();
    await expect(page.getByTestId("code-input")).toBeFocused();
    const otp = sb.sent.filter((r) => r.path === "/auth/v1/otp");
    expect(otp).toHaveLength(1);
    expect(JSON.parse(otp[0]!.body)).toMatchObject({ email: USER.email });

    // Too short: refused here, nothing sent.
    await page.getByTestId("code-input").fill("12345");
    await page.getByTestId("code-verify").click();
    await expect(page.getByTestId("code-problem")).toContainText("6 to 10 digits");
    expect(sb.sent.filter((r) => r.path === "/auth/v1/verify")).toHaveLength(0);

    // Wrong: the service says no.
    await page.getByTestId("code-input").fill("87654321");
    await page.getByTestId("code-verify").click();
    await expect(page.getByTestId("code-problem")).toContainText("expired or has already been used");

    // Right (8 digits, with a space as pasted from some mail apps).
    await page.getByTestId("code-input").fill("1234 5678");
    await page.getByTestId("code-verify").click();
    await expect(page.getByTestId("tp-account")).toContainText(USER.email);
    const verify = sb.sent.filter((r) => r.path === "/auth/v1/verify");
    expect(JSON.parse(verify.at(-1)!.body)).toMatchObject({ email: USER.email, token: "12345678", type: "email" });
    // The session lives in this pane's own storage (supabase-js's key), nowhere else.
    const keys = await page.evaluate(() => Object.keys(localStorage));
    expect(keys.some((k) => k.startsWith("sb-researchlye2e-auth-token"))).toBe(true);
  });

  test("axe: the sign-in steps have no serious violations", async ({ page }) => {
    await mockSupabase(page);
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    await page.setViewportSize({ width: 375, height: 760 });
    await page.goto("/word");
    await page.getByTestId("tp-sign-in").click();
    await page.getByTestId("code-email").fill(USER.email);
    await page.getByTestId("code-send").click();
    await expect(page.getByTestId("code-input")).toBeVisible();
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("Word taskpane, signed in", () => {
  test("the bearer token goes to the cloud engine; mute and add-to-dictionary use the account, then re-check", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page);
    await fakeOffice(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, { ...reviseResponse, signed_in: true }));
    await page.goto("/word");
    await expect(page.getByTestId("tp-account")).toContainText(USER.email);
    await check(page);
    const word = () => calls.filter((c) => c.path === "/v1/analyze-word");
    expect(tokenLabel(word()[0]!.authorization)).toBe("initial");

    await card(page, "In order to").getByTestId("mute-rule").click();
    await expect(page.getByTestId("account-note")).toContainText("Muted “Wordy phrase”");
    expect(sb.sent.some((r) => r.path === "/rest/v1/rpc/mute_rule" && JSON.parse(r.body).rule_id === "C120")).toBe(true);
    await expect.poll(() => word().length).toBe(2);

    await card(page, "nowcasting").getByTestId("add-word").click();
    await expect(page.getByTestId("account-note")).toContainText("Added “nowcasting” to your dictionary");
    expect(sb.words).toContain("nowcasting");
    await expect.poll(() => word().length).toBe(3);
  });

  test("Draft/Revise is saved to the account and read back from it", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, { settings: { disabled_rules: [], show_preferences: false, locale: "en-GB", mode: "draft" } });
    await fakeOffice(page);
    const calls = await mockEngineAuth(page, (c, route) =>
      reply(route, 200, (c.json as { options?: { mode?: string } }).options?.mode === "draft" ? draftResponse : reviseResponse),
    );
    await page.goto("/word");
    // From the account, not from this computer.
    await expect(page.getByTestId("mode-draft")).toBeChecked();
    await check(page);
    expect((calls.find((c) => c.path === "/v1/analyze-word")!.json as { options: { mode: string } }).options.mode).toBe("draft");
    await expect(page.getByTestId("held-back")).toBeVisible();

    await page.getByTestId("mode-revise").check();
    await expect.poll(() => sb.settings?.mode).toBe("revise");
    const upsert = sb.sent.find((r) => r.path === "/rest/v1/user_settings" && r.method === "POST");
    expect(JSON.parse(upsert!.body)).toEqual({ mode: "revise" });
  });

  test("the article type is saved to the account and read back from it (S4)", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, {
      settings: { disabled_rules: [], show_preferences: false, locale: "en-GB", document_type: "thesis-chapter" },
    });
    await fakeOffice(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, { ...reviseResponse, signed_in: true }));
    await page.goto("/word");
    // From the account, not from this computer.
    await expect(page.getByTestId("document-type")).toHaveValue("thesis-chapter");
    await check(page);
    const typeOf = (i: number) =>
      (calls.filter((c) => c.path === "/v1/analyze-word")[i]!.json as { options: { document_type: string } }).options.document_type;
    expect(typeOf(0)).toBe("thesis-chapter");

    await page.getByTestId("document-type").selectOption("grant");
    await expect.poll(() => sb.settings?.document_type).toBe("grant");
    const upsert = sb.sent.find((r) => r.path === "/rest/v1/user_settings" && r.method === "POST");
    expect(JSON.parse(upsert!.body)).toEqual({ document_type: "grant" });
    // A changed type checks again, as a changed stage does.
    await expect.poll(() => calls.filter((c) => c.path === "/v1/analyze-word").length).toBe(2);
    expect(typeOf(1)).toBe("grant");
  });

  test("a failed save of Draft/Revise is said, and the choice still applies here", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    await page.route("https://researchlye2e.supabase.co/rest/v1/user_settings*", (route) =>
      route.request().method() === "POST"
        ? reply(route, 500, { code: "XX000", message: "boom" })
        : reply(route, 200, []),
    );
    await page.goto("/word");
    await page.getByTestId("mode-draft").check();
    await expect(page.getByTestId("mode-note")).toContainText("could not be saved to your account");
    await expect(page.getByTestId("mode-draft")).toBeChecked();
  });

  test("“This computer” gets no token, but does get the account's muted rules", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page, { settings: { disabled_rules: ["G101"], show_preferences: false, locale: "en-US" } });
    await fakeOffice(page);
    const cloud = await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    const local = await mockWordEngine(page, LOCAL_ENGINE);
    await page.goto("/word");
    await page.getByTestId("tp-settings").locator("summary").click();
    await page.getByTestId("engine-local").check();
    await check(page);
    expect(local).toHaveLength(1);
    expect(local[0]!.authorization).toBeUndefined();
    expect(local[0]!.body.options?.disabled_rules).toEqual(["G101"]);
    expect(cloud.filter((c) => c.path === "/v1/analyze-word")).toHaveLength(0);
  });

  test("sign out from the settings area", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    await fakeOffice(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, reviseResponse));
    await page.goto("/word");
    await page.getByTestId("tp-settings").locator("summary").click();
    await page.getByTestId("tp-sign-out").click();
    await expect(page.getByTestId("tp-sign-in")).toBeVisible();
  });
});

