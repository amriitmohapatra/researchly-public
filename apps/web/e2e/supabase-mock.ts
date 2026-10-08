/**
 * A mocked Supabase project and an auth-aware mocked engine for the
 * "accounts" e2e project (playwright.config.ts). Everything is in memory and
 * intercepted with page.route: no network, no real Supabase.
 *
 * supabase-js keeps its session in localStorage under
 * `sb-<project-ref>-auth-token`; seedSession() puts one there before the page
 * loads, as if the user had signed in earlier.
 */
import type { Page, Route } from "@playwright/test";
import type { RuleInfo } from "@researchly/contract";
import { PROFILES } from "./fixtures";

export const SUPABASE_URL = "https://researchlye2e.supabase.co";
export const SUPABASE_KEY = "sb_publishable_e2e_mock_key_0000";
export const STORAGE_KEY = "sb-researchlye2e-auth-token";
export const ENGINE = "http://127.0.0.1:8099";

export const USER = { id: "11111111-1111-4111-8111-111111111111", email: "amira.k@example.ac.uk" };
/** Someone else: their id must never appear in anything this browser sends. */
export const OTHER_USER_ID = "22222222-2222-4222-8222-222222222222";

function b64url(v: unknown): string {
  return Buffer.from(JSON.stringify(v)).toString("base64url");
}

/** A JWT-shaped access token. Its `label` lets tests tell tokens apart (initial / refreshed). */
export function accessToken(label: string): string {
  const now = Math.floor(Date.now() / 1000);
  const payload = { sub: USER.id, aud: "authenticated", role: "authenticated", email: USER.email, exp: now + 3600, iat: now, session_id: label };
  return `${b64url({ alg: "ES256", typ: "JWT", kid: "e2e" })}.${b64url(payload)}.sig-${label}`;
}

export function session(label: string) {
  const now = Math.floor(Date.now() / 1000);
  return {
    access_token: accessToken(label),
    refresh_token: `refresh-${label}`,
    token_type: "bearer",
    expires_in: 3600,
    expires_at: now + 3600,
    user: {
      id: USER.id,
      aud: "authenticated",
      role: "authenticated",
      email: USER.email,
      email_confirmed_at: "2026-10-01T09:00:00Z",
      app_metadata: { provider: "email", providers: ["email"] },
      user_metadata: {},
      created_at: "2026-10-01T09:00:00Z",
      updated_at: "2026-10-01T09:00:00Z",
    },
  };
}

/** Signed in before the page loads (once per test: a reload after signing out stays signed out). */
export async function seedSession(page: Page) {
  await page.addInitScript(
    ([key, value]) => {
      if (window.sessionStorage.getItem("e2e-seeded")) return;
      window.localStorage.setItem(key, value);
      window.sessionStorage.setItem("e2e-seeded", "1");
    },
    [STORAGE_KEY, JSON.stringify(session("initial"))] as const,
  );
}

function cors(route: Route): Record<string, string> {
  const req = route.request().headers();
  return {
    "access-control-allow-origin": req["origin"] ?? "*",
    "access-control-allow-methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
    "access-control-allow-headers": req["access-control-request-headers"] ?? "authorization, content-type",
    "access-control-expose-headers": "content-range, retry-after, x-request-id",
    "access-control-max-age": "600",
  };
}

export async function reply(route: Route, status: number, body?: unknown, headers: Record<string, string> = {}) {
  await route.fulfill({
    status,
    headers: { ...cors(route), ...(body === undefined ? {} : { "content-type": "application/json" }), ...headers },
    body: body === undefined ? "" : JSON.stringify(body),
  });
}

export interface SentRequest {
  method: string;
  path: string;
  search: string;
  headers: Record<string, string>;
  body: string;
}

export interface SupabaseState {
  settings: {
    disabled_rules: string[];
    show_preferences: boolean;
    locale: string;
    mode?: string;
    document_type?: string;
    keep_progress?: boolean;
  } | null;
  words: string[];
  /** progress_events rows (S4c): counts only. Inserts are refused unless settings.keep_progress, as the migration's policy does. */
  progress: { created_at: string; words: number; document_type: string; counts: Record<string, number> }[];
  /** Response for POST /auth/v1/otp (default: 200 {}). */
  otp: { status: number; body: unknown } | null;
  /** Response for POST /auth/v1/verify (the emailed code, S3). Default: a session when the token is "12345678". */
  verify: { status: number; body: unknown } | null;
  /** Make the refresh-token grant fail (a revoked session). */
  refreshFails: boolean;
  /** Every request this browser sent to Supabase, for assertions. */
  sent: SentRequest[];
}

/** Mock Supabase Auth and the two settings tables. */
export async function mockSupabase(page: Page, init: Partial<SupabaseState> = {}): Promise<SupabaseState> {
  const state: SupabaseState = {
    settings: null,
    words: [],
    progress: [],
    otp: null,
    verify: null,
    refreshFails: false,
    sent: [],
    ...init,
  };
  await page.route(`${SUPABASE_URL}/**`, async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return reply(route, 204);
    const url = new URL(req.url());
    state.sent.push({
      method: req.method(),
      path: url.pathname,
      search: url.search,
      headers: req.headers(),
      body: req.postData() ?? "",
    });
    const p = url.pathname;

    if (p === "/auth/v1/token") {
      const grant = url.searchParams.get("grant_type");
      if (grant === "refresh_token" && state.refreshFails) {
        return reply(route, 400, { code: 400, error_code: "refresh_token_not_found", msg: "Invalid Refresh Token" });
      }
      return reply(route, 200, session(grant === "pkce" ? "pkce" : "refreshed"));
    }
    if (p === "/auth/v1/otp") return reply(route, state.otp?.status ?? 200, state.otp?.body ?? {});
    if (p === "/auth/v1/verify") {
      if (state.verify) return reply(route, state.verify.status, state.verify.body);
      const { token } = JSON.parse(req.postData() || "{}") as { token?: string };
      return token === "12345678"
        ? reply(route, 200, session("otp"))
        : reply(route, 403, { code: 403, error_code: "otp_expired", msg: "Token has expired or is invalid" });
    }
    if (p === "/auth/v1/logout") return reply(route, 204);
    if (p === "/auth/v1/user") return reply(route, 200, session("initial").user);

    if (p === "/rest/v1/user_settings") {
      if (req.method() === "GET") return reply(route, 200, state.settings ? [state.settings] : []);
      if (req.method() === "POST") {
        const patch = JSON.parse(req.postData() || "{}") as Record<string, unknown>;
        // The table's defaults (supabase/migrations): locale en-US.
        const base = state.settings ?? { disabled_rules: [], show_preferences: false, locale: "en-US" };
        const next = { ...base, ...patch } as Record<string, unknown>;
        delete next.updated_at;
        delete next.user_id;
        state.settings = next as SupabaseState["settings"];
        return reply(route, 201, [state.settings]);
      }
      if (req.method() === "DELETE") {
        state.settings = null;
        return reply(route, 204);
      }
    }
    if (p === "/rest/v1/rpc/mute_rule" || p === "/rest/v1/rpc/unmute_rule") {
      // As the migration: one rule, changed in place, on the caller's own row.
      const { rule_id } = JSON.parse(req.postData() || "{}") as { rule_id: string };
      const base = state.settings ?? { disabled_rules: [], show_preferences: false, locale: "en-US" };
      const rules = base.disabled_rules.filter((r) => r !== rule_id);
      if (p.endsWith("/mute_rule")) rules.push(rule_id);
      else if (!state.settings) return reply(route, 200, null);
      state.settings = { ...base, disabled_rules: rules };
      return reply(route, 200, rules);
    }
    if (p === "/rest/v1/progress_events") {
      if (req.method() === "GET") {
        // Newest first, as loadProgress asks (order=created_at.desc).
        const rows = [...state.progress].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
        return reply(route, 200, rows);
      }
      if (req.method() === "POST") {
        if (state.settings?.keep_progress !== true) {
          return reply(route, 403, { code: "42501", message: "new row violates row-level security policy" });
        }
        const row = JSON.parse(req.postData() || "{}") as SupabaseState["progress"][number];
        state.progress.push({ ...row, created_at: new Date(Date.now() + state.progress.length).toISOString() });
        return reply(route, 201);
      }
      if (req.method() === "DELETE") {
        if (url.searchParams.get("user_id")) state.progress = [];
        return reply(route, 204);
      }
    }
    if (p === "/rest/v1/dictionary_words") {
      if (req.method() === "GET") return reply(route, 200, [...state.words].sort().map((word) => ({ word })));
      if (req.method() === "POST") {
        const row = JSON.parse(req.postData() || "{}") as { word: string };
        if (state.words.includes(row.word)) {
          return reply(route, 409, { code: "23505", message: "duplicate key value violates unique constraint" });
        }
        state.words.push(row.word);
        return reply(route, 201);
      }
      if (req.method() === "DELETE") {
        const word = url.searchParams.get("word")?.replace(/^eq\./, "");
        if (word) state.words = state.words.filter((w) => w !== word);
        else if (url.searchParams.get("user_id")) state.words = [];
        return reply(route, 204);
      }
    }
    return reply(route, 404, { message: `unmocked ${req.method()} ${p}` });
  });
  return state;
}

export interface EngineCall {
  path: string;
  authorization: string | undefined;
  headers: Record<string, string>;
  /** JSON body for /v1/analyze; for /v1/analyze-file, the size of the raw body. */
  json: unknown;
  bytes: number;
}

export type EngineHandler = (call: EngineCall, route: Route, n: number) => Promise<void> | void;

/** Mock the engine's /v1/analyze, /v1/analyze-file and /v1/rules, recording the Authorization header. */
export async function mockEngineAuth(page: Page, handler: EngineHandler, rules: RuleInfo[] = []): Promise<EngineCall[]> {
  const calls: EngineCall[] = [];
  await page.route(`${ENGINE}/v1/**`, async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return reply(route, 204);
    const path = new URL(req.url()).pathname;
    if (path === "/v1/rules") return reply(route, 200, { rules, profiles: PROFILES });
    if (path === "/v1/health") return reply(route, 200, { status: "ok", tiers: [], engine: { service_version: "0", core_version: "0", rules_loaded: 0 } });
    const buf = req.postDataBuffer();
    const headers = req.headers();
    const call: EngineCall = {
      path,
      authorization: headers["authorization"],
      headers,
      json: path === "/v1/analyze" || path === "/v1/analyze-word" ? req.postDataJSON() : null,
      bytes: buf?.length ?? 0,
    };
    calls.push(call);
    await handler(call, route, calls.length);
  });
  return calls;
}
