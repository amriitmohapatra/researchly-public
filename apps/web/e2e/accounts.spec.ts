/**
 * S2: accounts, uploads and synced settings, against the build made WITH a
 * (mocked) Supabase project. See playwright.config.ts, project "accounts".
 */
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  afterAddWord,
  afterMute,
  authUnavailable,
  mdResponse,
  MD_TEXT,
  PASTE_TEXT,
  RULES,
  signedInPaste,
  signInRequired,
  unauthorized,
  zipResponse,
} from "./accounts-fixtures";
import {
  ENGINE,
  mockEngineAuth,
  mockSupabase,
  OTHER_USER_ID,
  reply,
  seedSession,
  STORAGE_KEY,
  SUPABASE_URL,
  USER,
} from "./supabase-mock";

const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function axeSerious(page: Page, tags = AXE_TAGS) {
  const r = await new AxeBuilder({ page }).withTags(tags).analyze();
  return r.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`);
}

async function pasteAndCheck(page: Page, text = PASTE_TEXT) {
  await page.getByLabel("Text to check").fill(text);
  await page.getByTestId("check").click();
}

/** Tokens embed a timestamp; compare by the label baked into the signature. */
const tokenLabel = (h: string | undefined) => h?.match(/\.sig-([a-z]+)$/)?.[1];

test.describe("signed out, with accounts configured", () => {
  test("the header offers sign-in; pasting still works anonymously, with no bearer token", async ({ page }) => {
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, { ...signedInPaste, signed_in: false }));
    await page.goto("/");
    await expect(page.getByTestId("sign-in")).toBeVisible();
    await expect(page.getByTestId("upload-row")).toContainText("Needs an account");
    await pasteAndCheck(page);
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
    expect(calls[0]!.authorization).toBeUndefined();
    // Signed out, cards carry no account actions.
    await expect(page.getByTestId("mute-rule")).toHaveCount(0);
    await expect(page.getByTestId("add-word")).toHaveCount(0);
  });

  test("choosing a file explains it needs an account, and sends nothing", async ({ page }) => {
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, mdResponse));
    await page.goto("/");
    await page.getByTestId("choose-file").click();
    const dialog = page.getByTestId("sign-in-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Checking a file needs an account");
    await expect(page.getByTestId("sign-in-email")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByTestId("choose-file")).toBeFocused();
    expect(calls).toHaveLength(0);
  });

  test("sign_in_required (too long without an account) shows a sign-in prompt in place of results", async ({ page }) => {
    await mockSupabase(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 401, signInRequired));
    await page.goto("/");
    await pasteAndCheck(page);
    const prompt = page.getByTestId("sign-in-prompt");
    await expect(prompt).toBeVisible();
    await expect(prompt).toContainText("Sign in to check this much text");
    await expect(prompt).toContainText("1,500 words");
    await expect(prompt).toBeFocused();
    await expect(page.getByTestId("results")).toHaveCount(0);
    await expect(page.getByLabel("Text to check")).toHaveValue(PASTE_TEXT);
    await prompt.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByTestId("sign-in-dialog")).toBeVisible();
    expect(await axeSerious(page)).toEqual([]);
  });
});

test.describe("sign-in", () => {
  test("magic link: asks Supabase from the browser with a redirect back to this site", async ({ page, baseURL }) => {
    const sb = await mockSupabase(page);
    const own: string[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith(baseURL!) && r.method() !== "GET") own.push(r.url());
    });
    await page.goto("/");
    await page.getByTestId("sign-in").click();
    await page.getByTestId("sign-in-email").fill("not-an-address");
    await page.getByTestId("sign-in-send").click();
    await expect(page.getByTestId("sign-in-problem")).toContainText("Enter your email address");
    expect(sb.sent.filter((r) => r.path === "/auth/v1/otp")).toHaveLength(0);

    await page.getByTestId("sign-in-email").fill(USER.email);
    await page.getByTestId("sign-in-send").click();
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await expect(page.getByTestId("sign-in-dialog")).toContainText(USER.email);
    const otp = sb.sent.find((r) => r.path === "/auth/v1/otp")!;
    expect(otp.method).toBe("POST");
    expect(new URLSearchParams(otp.search).get("redirect_to")).toBe(baseURL);
    const body = JSON.parse(otp.body) as { email: string; code_challenge?: string; code_challenge_method?: string };
    expect(body.email).toBe(USER.email);
    // PKCE: the code is exchanged in this browser, never by the Next.js server.
    expect(body.code_challenge).toBeTruthy();
    expect(body.code_challenge_method?.toLowerCase()).toBe("s256");
    expect(own).toEqual([]);
    expect(await axeSerious(page)).toEqual([]);
  });

  test("a Supabase error becomes a clear message", async ({ page }) => {
    await mockSupabase(page, {
      otp: { status: 429, body: { code: 429, error_code: "over_email_send_rate_limit", msg: "email rate limit exceeded" } },
    });
    await page.goto("/");
    await page.getByTestId("sign-in").click();
    await page.getByTestId("sign-in-email").fill(USER.email);
    await page.getByTestId("sign-in-send").click();
    await expect(page.getByTestId("sign-in-problem")).toContainText("Too many sign-in emails");
    await expect(page.getByTestId("sign-in-problem")).not.toContainText("rate limit exceeded");
  });

  test("the link's code is exchanged in the browser, then removed from the address bar", async ({ page }) => {
    const sb = await mockSupabase(page);
    await page.addInitScript((key) => window.localStorage.setItem(`${key}-code-verifier`, JSON.stringify("e2e-verifier-0123456789")), STORAGE_KEY);
    await page.goto("/?code=e2e-auth-code");
    await expect(page.getByTestId("account-button")).toContainText(USER.email);
    const exchange = sb.sent.find((r) => r.path === "/auth/v1/token")!;
    expect(new URLSearchParams(exchange.search).get("grant_type")).toBe("pkce");
    expect(JSON.parse(exchange.body)).toMatchObject({ auth_code: "e2e-auth-code", code_verifier: "e2e-verifier-0123456789" });
    await expect.poll(() => new URL(page.url()).search).toBe("");
  });

  test("an expired link says so and offers a new one", async ({ page }) => {
    await mockSupabase(page);
    await page.goto("/#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired");
    await expect(page.getByTestId("sign-in-dialog")).toBeVisible();
    await expect(page.getByTestId("sign-in-notice")).toContainText("expired or has already been used");
    await expect.poll(() => new URL(page.url()).hash).toBe("");
  });
});

test.describe("signed in", () => {
  test("the check sends the bearer token; the account menu works from the keyboard", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, signedInPaste));
    await page.goto("/");
    const menu = page.getByTestId("account-button");
    await expect(menu).toContainText(USER.email);
    await pasteAndCheck(page);
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
    expect(tokenLabel(calls[0]!.authorization)).toBe("initial");
    expect(calls[0]!.authorization).toMatch(/^Bearer [\w-]+\.[\w-]+\.[\w-]+$/);
    expect(calls[0]!.json).toEqual({
      content: PASTE_TEXT,
      format: "plain",
      options: { show_preferences: false, document_type: "auto", review: true, narrative: true, mode: "revise" },
    });

    await menu.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByTestId("account-panel")).toContainText("Signed in as");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Settings and dictionary" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("account-panel")).toBeHidden();
    await expect(menu).toBeFocused();
    expect(await axeSerious(page, [...AXE_TAGS, "best-practice"])).toEqual([]);
  });

  test("the article type comes from the account, and a change is saved to it and checked again (S4)", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, {
      settings: { disabled_rules: [], show_preferences: false, locale: "en-US", document_type: "manuscript" },
    });
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, signedInPaste));
    await page.goto("/");
    // From the account, not from this browser.
    await expect(page.getByLabel("Check as")).toHaveValue("manuscript");
    await pasteAndCheck(page);
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
    const typeOf = (i: number) => (calls[i]!.json as { options: { document_type: string } }).options.document_type;
    expect(typeOf(0)).toBe("manuscript");

    await page.getByLabel("Check as").selectOption("abstract");
    await expect.poll(() => sb.settings?.document_type).toBe("abstract");
    const upsert = sb.sent.find((r) => r.path === "/rest/v1/user_settings" && r.method === "POST");
    expect(JSON.parse(upsert!.body)).toEqual({ document_type: "abstract" });
    await expect.poll(() => calls.length).toBe(2);
    expect(typeOf(1)).toBe("abstract");
  });

  test("401 unauthorized: refresh once, retry once with the new token", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page);
    const calls = await mockEngineAuth(page, (c, route) =>
      tokenLabel(c.authorization) === "refreshed" ? reply(route, 200, signedInPaste) : reply(route, 401, unauthorized),
    );
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
    expect(calls.map((c) => tokenLabel(c.authorization))).toEqual(["initial", "refreshed"]);
    const refreshes = sb.sent.filter((r) => r.path === "/auth/v1/token" && r.search.includes("refresh_token"));
    expect(refreshes).toHaveLength(1);
    await expect(page.getByTestId("account-button")).toBeVisible();
  });

  test("401 again after the refresh: signed out locally, with a message; the text stays", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 401, unauthorized));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    const err = page.getByTestId("check-error");
    await expect(err).toHaveAttribute("data-kind", "signed_out");
    await expect(err).toContainText("You have been signed out");
    expect(calls).toHaveLength(2); // one retry, never a silent anonymous third attempt
    expect(calls.every((c) => c.authorization)).toBe(true);
    await expect(page.getByTestId("sign-in")).toBeVisible();
    await expect(page.getByLabel("Text to check")).toHaveValue(PASTE_TEXT);
    expect(await page.evaluate((k) => window.localStorage.getItem(k), STORAGE_KEY)).toBeNull();
  });

  test("503 auth_unavailable is a retryable error", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    let up = false;
    await mockEngineAuth(page, (_c, route) => (up ? reply(route, 200, signedInPaste) : reply(route, 503, authUnavailable)));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    const err = page.getByTestId("check-error");
    await expect(err).toHaveAttribute("data-kind", "auth_unavailable");
    await expect(err).toContainText("could not be checked just now");
    up = true;
    await page.getByTestId("retry").click();
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
  });

  test("Mute this rule: saved to the account (own row only), then the check re-runs", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route, n) => reply(route, 200, n === 1 ? signedInPaste : afterMute));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    const card = page.locator("#card-e2e-wordy-1");
    await card.getByTestId("mute-rule").click();
    await expect(page.getByTestId("account-note")).toContainText("Muted “Wordy phrase”");
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
    expect(calls).toHaveLength(2);
    expect(sb.settings?.disabled_rules).toEqual(["C120"]);
    // One atomic call, never read-modify-write of the whole list (a second tab
    // muting at the same moment would otherwise be lost).
    const mute = sb.sent.find((r) => r.method === "POST" && r.path === "/rest/v1/rpc/mute_rule")!;
    expect(JSON.parse(mute.body)).toEqual({ rule_id: "C120" });
    expect(sb.sent.some((r) => r.method === "POST" && r.path === "/rest/v1/user_settings")).toBe(false);
    for (const r of sb.sent) expect(r.body + r.search).not.toContain(OTHER_USER_ID);
    expect(await axeSerious(page)).toEqual([]);
  });

  test("Add to dictionary on a spelling card", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page);
    await mockEngineAuth(page, (_c, route, n) => reply(route, 200, n === 1 ? signedInPaste : afterAddWord));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    // Only the spelling card offers it.
    await expect(page.getByTestId("add-word")).toHaveCount(1);
    await page.locator("#card-e2e-spell-1").getByTestId("add-word").click();
    await expect(page.getByTestId("account-note")).toContainText("Added “nowcasting” to your dictionary");
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
    expect(sb.words).toEqual(["nowcasting"]);
    const insert = sb.sent.find((r) => r.method === "POST" && r.path === "/rest/v1/dictionary_words")!;
    expect(JSON.parse(insert.body)).toEqual({ word: "nowcasting" });
  });
});

test.describe("uploads", () => {
  test("a .md file: raw bytes, encoded name, bearer token; read-only view with highlights", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, mdResponse));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByLabel("Text to check").fill("My pasted draft stays here.");
    await page.getByTestId("file-input").setInputFiles({
      name: "Kapitel-ü 5.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(MD_TEXT, "utf8"),
    });
    await expect(page.getByTestId("file-panel")).toBeVisible();
    await expect(page.getByTestId("file-name")).toHaveText("Kapitel-ü 5.md");
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();

    const c = calls[0]!;
    expect(c.path).toBe("/v1/analyze-file");
    expect(c.headers["content-type"]).toBe("application/octet-stream");
    expect(c.headers["x-researchly-filename"]).toBe("Kapitel-%C3%BC%205.md");
    expect(JSON.parse(c.headers["x-researchly-options"]!)).toEqual({
      show_preferences: false,
      document_type: "auto",
      review: true,
      narrative: true,
      mode: "revise",
    });
    expect(tokenLabel(c.authorization)).toBe("initial");
    expect(c.bytes).toBe(Buffer.byteLength(MD_TEXT));

    await expect(page.getByTestId("file-panel")).toContainText("read-only");
    await expect(page.getByTestId("file-panel")).toContainText("Word or Overleaf");
    await expect(page.getByTestId("document")).toContainText("These results");
    await expect(page.getByTestId("document").locator('[data-sids~="e2e-md-1"]')).toHaveText("clearly prove");
    // A single file: no per-file location on cards.
    await expect(page.getByTestId("card-location")).toHaveCount(0);
    expect(await axeSerious(page)).toEqual([]);

    await page.getByTestId("back-to-editor").click();
    await expect(page.getByLabel("Text to check")).toHaveValue("My pasted draft stays here.");
    await expect(page.getByLabel("Text to check")).toBeFocused();
    await expect(page.getByTestId("file-panel")).toHaveCount(0);
  });

  test("an Overleaf .zip: each suggestion names its file and line; skipped inputs are listed", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, zipResponse));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByTestId("file-input").setInputFiles({
      name: "thesis-chapter.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK\u0003\u0004 synthetic"),
    });
    await expect(page.getByRole("heading", { name: "2 suggestions" })).toBeVisible();
    await expect(page.getByTestId("file-panel")).toContainText("LaTeX project, 2 files");
    await expect(page.getByTestId("file-warnings")).toContainText("\\input{appendix} not found");
    await expect(page.locator("#card-e2e-zip-1").getByTestId("card-location")).toHaveText("In file: main.tex, line 3");
    await expect(page.locator("#card-e2e-zip-2").getByTestId("card-location")).toHaveText(
      "In file: sections/methods.tex, line 3",
    );
    expect(await axeSerious(page)).toEqual([]);
  });

  test("drag and drop onto the editor checks the file", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, mdResponse));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    const dt = await page.evaluateHandle((text) => {
      const d = new DataTransfer();
      d.items.add(new File([text], "chapter-5.md", { type: "text/markdown" }));
      return d;
    }, MD_TEXT);
    const editor = page.getByLabel("Text to check");
    await editor.dispatchEvent("dragenter", { dataTransfer: dt });
    await expect(page.locator(".drop-overlay")).toContainText("Drop to check this file");
    await editor.dispatchEvent("drop", { dataTransfer: dt });
    await expect(page.getByTestId("file-name")).toHaveText("chapter-5.md");
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
    expect(calls[0]!.path).toBe("/v1/analyze-file");
  });

  test("Try again after a failed first file check re-sends the file, not the pasted text", async ({ page }) => {
    // Regression: retry used to fall back to the editor's text when no file result existed yet.
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route, n) => (n === 1 ? reply(route, 503, authUnavailable) : reply(route, 200, mdResponse)));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByLabel("Text to check").fill("Pasted draft.");
    await page.getByTestId("file-input").setInputFiles({ name: "chapter-5.md", mimeType: "text/markdown", buffer: Buffer.from(MD_TEXT) });
    await expect(page.getByTestId("check-error")).toHaveAttribute("data-kind", "auth_unavailable");
    await page.getByTestId("retry").click();
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
    expect(calls.map((c) => c.path)).toEqual(["/v1/analyze-file", "/v1/analyze-file"]);
  });

  test("cancelling a new version returns to the editor instead of an empty file panel", async ({ page }) => {
    // Regression: a stale earlier result made the cancel path keep the panel open with nothing in it.
    await seedSession(page);
    await mockSupabase(page);
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    await mockEngineAuth(page, async (_c, route, n) => {
      if (n === 2) await gate;
      await reply(route, 200, mdResponse);
    });
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByTestId("file-input").setInputFiles({ name: "chapter-5.md", mimeType: "text/markdown", buffer: Buffer.from(MD_TEXT) });
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
    await page.getByTestId("file-input").setInputFiles({ name: "chapter-6.md", mimeType: "text/markdown", buffer: Buffer.from(MD_TEXT) });
    await expect(page.getByTestId("file-name")).toHaveText("chapter-6.md");
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByTestId("file-panel")).toHaveCount(0);
    await expect(page.getByLabel("Text to check")).toBeVisible();
    release();
  });

  test("an unsupported type is refused in the browser, with no request", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    const calls = await mockEngineAuth(page, (_c, route) => reply(route, 200, mdResponse));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByTestId("file-input").setInputFiles({ name: "figure.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF") });
    await expect(page.getByTestId("file-problem")).toContainText(".pdf files can't be checked");
    expect(calls).toHaveLength(0);
  });

  test("the upload button is keyboard reachable and opens the file picker", async ({ page }) => {
    await seedSession(page);
    await mockSupabase(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, mdResponse));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await page.getByLabel("Text to check").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("choose-file")).toBeFocused();
    const chooser = page.waitForEvent("filechooser");
    await page.keyboard.press("Enter");
    await (await chooser).setFiles({ name: "chapter-5.md", mimeType: "text/markdown", buffer: Buffer.from(MD_TEXT) });
    await expect(page.getByRole("heading", { name: "1 suggestion" })).toBeVisible();
  });
});

test.describe("settings page", () => {
  test("signed out: asks to sign in", async ({ page }) => {
    await mockSupabase(page);
    await page.goto("/settings");
    await expect(page.getByTestId("settings-signed-out")).toContainText("Sign in to see your settings");
    expect(await axeSerious(page)).toEqual([]);
  });

  test("load, unmute, switch, locale, add and remove words, delete: own rows only", async ({ page }) => {
    await seedSession(page);
    const sb = await mockSupabase(page, {
      settings: { disabled_rules: ["C120", "G101"], show_preferences: false, locale: "en-GB" },
      words: ["Rt", "nowcasting"],
    });
    await mockEngineAuth(page, (_c, route) => reply(route, 200, signedInPaste), RULES);
    await page.goto("/settings");
    const muted = page.getByTestId("muted-rule");
    await expect(muted).toHaveCount(2);
    await expect(muted.first()).toContainText("Wordy phrase");
    await expect(muted.first()).toContainText("Prefer the shorter phrase");
    await expect(page.getByTestId("word-count")).toHaveText("2 of 5,000 words");
    expect(await axeSerious(page, [...AXE_TAGS, "best-practice"])).toEqual([]);

    await page.getByRole("button", { name: "Unmute Wordy phrase" }).click();
    await expect(page.getByTestId("settings-status")).toHaveText("Unmuted Wordy phrase.");
    await expect(muted).toHaveCount(1);
    expect(sb.settings?.disabled_rules).toEqual(["G101"]);

    await page.getByTestId("settings-show-preferences").check();
    await expect(page.getByTestId("settings-status")).toHaveText("Preferences will be shown.");
    expect(sb.settings?.show_preferences).toBe(true);

    await page.getByTestId("locale-en-US").check();
    await expect(page.getByTestId("settings-status")).toHaveText("Spelling set to American English.");
    expect(sb.settings?.locale).toBe("en-US");

    // Limits are explained before anything is sent.
    await page.getByTestId("word-input").fill("two words");
    await page.getByTestId("word-add").click();
    await expect(page.getByTestId("word-problem")).toContainText("no spaces");
    await page.getByTestId("word-input").fill("x".repeat(65));
    await page.getByTestId("word-add").click();
    await expect(page.getByTestId("word-problem")).toContainText("64 characters");
    await page.getByTestId("word-input").fill("serial-interval");
    await page.getByTestId("word-add").click();
    await expect(page.getByTestId("settings-status")).toHaveText("Added “serial-interval” to your dictionary.");
    await expect(page.getByTestId("word-count")).toHaveText("3 of 5,000 words");
    await expect(page.getByTestId("word-input")).toHaveValue("");

    await page.getByRole("button", { name: "Remove Rt" }).click();
    await expect(page.getByTestId("settings-status")).toHaveText("Removed “Rt” from your dictionary.");
    expect(sb.words).toEqual(["nowcasting", "serial-interval"]);

    await page.getByTestId("delete-open").click();
    const dialog = page.getByTestId("delete-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Keep them" })).toBeFocused();
    expect(await axeSerious(page)).toEqual([]);
    await dialog.getByTestId("delete-confirm").click();
    await expect(page.getByTestId("settings-status")).toHaveText("Your settings, dictionary and progress were deleted.");
    await expect(dialog).toBeHidden();
    await expect(page.getByTestId("muted-empty")).toBeVisible();
    await expect(page.getByTestId("word-count")).toHaveText("Your dictionary is empty.");
    expect(sb.settings).toBeNull();
    expect(sb.words).toEqual([]);

    const deletes = sb.sent.filter((r) => r.method === "DELETE");
    // "Delete my data": progress first (S4c), then the dictionary and the settings, each by the caller's own id.
    const wholesale = deletes.filter((r) => r.search.includes(`user_id=eq.${USER.id}`)).map((r) => r.path);
    expect(wholesale[0]).toBe("/rest/v1/progress_events");
    expect(deletes.some((r) => r.path === "/rest/v1/user_settings" && r.search.includes(`user_id=eq.${USER.id}`))).toBe(true);
    expect(deletes.some((r) => r.path === "/rest/v1/dictionary_words" && r.search.includes(`user_id=eq.${USER.id}`))).toBe(true);
    // Never another user's id; inserts and upserts carry no user id at all (the column defaults to auth.uid()).
    for (const r of sb.sent) {
      expect(r.body + r.search).not.toContain(OTHER_USER_ID);
      if (r.method === "POST" && r.path.startsWith("/rest/")) expect(JSON.parse(r.body)).not.toHaveProperty("user_id");
    }
  });
});

test.describe("security and privacy with accounts", () => {
  test("CSP connect-src adds exactly the Supabase origin", async ({ request }) => {
    const res = await request.get("/");
    const csp = res.headers()["content-security-policy"]!;
    expect(csp).toMatch(new RegExp(`connect-src 'self' ${ENGINE.replace(/[.:/]/g, "\\$&")} ${SUPABASE_URL.replace(/[.:/]/g, "\\$&")}(;|$)`));
    expect(csp).not.toContain("unsafe-inline");
    expect(res.headers()["set-cookie"]).toBeUndefined();
  });

  test("no console errors, no third parties, no cookies; storage holds the session and the format only", async ({ page, baseURL }) => {
    const problems: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") problems.push(m.text());
    });
    page.on("pageerror", (e) => problems.push(e.message));
    const external: string[] = [];
    page.on("request", (r) => {
      const u = r.url();
      if (![baseURL!, ENGINE, SUPABASE_URL, "data:"].some((p) => u.startsWith(p))) external.push(u);
    });
    await seedSession(page);
    await mockSupabase(page);
    await mockEngineAuth(page, (_c, route) => reply(route, 200, signedInPaste));
    await page.goto("/");
    await expect(page.getByTestId("account-button")).toBeVisible();
    await pasteAndCheck(page);
    await expect(page.getByTestId("suggestion-card")).toHaveCount(2);
    expect(problems).toEqual([]);
    expect(external).toEqual([]);
    expect(await page.context().cookies()).toEqual([]);
    const stored = await page.evaluate(() => ({
      keys: Object.keys(window.localStorage).sort(),
      values: Object.values(window.localStorage).join(""),
    }));
    expect(stored.keys.every((k) => k === STORAGE_KEY || k === "researchly.format")).toBe(true);
    expect(stored.values).not.toContain("nowcasting model");
  });
});

for (const width of [375, 1280]) {
  test.describe(`responsive ${width}px`, () => {
    test.use({ viewport: { width, height: width === 375 ? 812 : 900 } });
    const shots = process.env.SHOTS_DIR ?? "test-results/shots";
    const noOverflow = (page: Page) =>
      page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

    test("checker with account actions, file view and settings: no horizontal scroll", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await seedSession(page);
      await mockSupabase(page, {
        settings: { disabled_rules: ["C120", "G101"], show_preferences: false, locale: "en-GB" },
        words: ["nowcasting", "Rt", "serial-interval", "a-very-long-hyphenated-term-from-the-field-of-epidemiology"],
      });
      await mockEngineAuth(page, (c, route) => reply(route, 200, c.path === "/v1/analyze-file" ? zipResponse : signedInPaste), RULES);

      await page.goto("/");
      await expect(page.getByTestId("account-button")).toBeVisible();
      await pasteAndCheck(page);
      await expect(page.getByTestId("suggestion-card").first()).toBeVisible();
      await page.getByTestId("suggestion-card").first().getByText("The full reasoning").click();
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${shots}/accounts-checker-${width}.png`, fullPage: true });

      await page.getByTestId("account-button").click();
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${shots}/accounts-menu-${width}.png` });
      await page.keyboard.press("Escape");

      await page.getByTestId("file-input").setInputFiles({ name: "thesis-chapter.zip", mimeType: "application/zip", buffer: Buffer.from("PK") });
      await expect(page.getByTestId("card-location").first()).toBeVisible();
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${shots}/accounts-file-${width}.png`, fullPage: true });

      await page.goto("/settings");
      await expect(page.getByTestId("muted-rule")).toHaveCount(2);
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${shots}/accounts-settings-${width}.png`, fullPage: true });

      await page.getByTestId("delete-open").click();
      await expect(page.getByTestId("delete-dialog")).toBeVisible();
      await page.screenshot({ path: `${shots}/accounts-delete-dialog-${width}.png` });
    });

    test("signed out: sign-in dialog fits", async ({ page }) => {
      await mockSupabase(page);
      await page.goto("/");
      await page.getByTestId("sign-in").click();
      await expect(page.getByTestId("sign-in-dialog")).toBeVisible();
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${shots}/accounts-sign-in-${width}.png` });
    });
  });
}

test("dark mode: no serious axe violations on signed-in results and settings", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await seedSession(page);
  await mockSupabase(page, { settings: { disabled_rules: ["C120"], show_preferences: false, locale: "en-GB" }, words: ["Rt"] });
  await mockEngineAuth(page, (_c, route) => reply(route, 200, zipResponse), RULES);
  await page.goto("/");
  await expect(page.getByTestId("account-button")).toBeVisible();
  await page.getByTestId("file-input").setInputFiles({ name: "thesis-chapter.zip", mimeType: "application/zip", buffer: Buffer.from("PK") });
  await expect(page.getByTestId("card-location").first()).toBeVisible();
  expect(await axeSerious(page, [...AXE_TAGS, "best-practice"])).toEqual([]);
  await page.goto("/settings");
  await expect(page.getByTestId("muted-rule")).toHaveCount(1);
  expect(await axeSerious(page, [...AXE_TAGS, "best-practice"])).toEqual([]);
});
