/**
 * The only code that sends document text anywhere. It runs in the browser
 * and talks straight to the engine (ADR-02 / ARCHITECTURE.md §5.3): the
 * Next.js server never receives the text. `client-only` makes importing
 * this module from server code a build error, and scripts/check-boundary.mjs
 * fails the lint if any route handler or server action appears.
 *
 * S2: when signed in, requests carry `Authorization: Bearer <access token>`
 * so the engine applies the account's settings (docs/s2-design.md §3). The
 * token is read from supabase-js at call time and never stored here.
 */
import "client-only";
import type {
  AnalyzeOptions,
  ChecklistChoice,
  ChecklistChoiceInfo,
  AnalyzeFileResponse,
  AnalyzeRequest,
  AnalyzeResponse,
  AnalyzeWordRequest,
  AnalyzeWordResponse,
  DocumentType,
  Format,
  HealthResponse,
  Mode,
  ProfileChoice,
  RuleInfo,
  WordParagraph,
} from "@researchly/contract";
import { ENGINE_URL } from "./config";
import {
  badPayloadError,
  errorFromResponse,
  networkError,
  refreshUnavailableError,
  signedOutError,
  type CheckError,
} from "./errors";

/**
 * How long the browser waits for one check. Just under the engine's own
 * request timeout (services/engine/deploy/cloudrun.service.yaml,
 * timeoutSeconds: 300), so the browser never gives up on a check the engine
 * is still allowed to finish. A whole thesis (~120k words) takes about two
 * minutes on Cloud Run; 120 s here abandoned it just before the end.
 * Pinned by tests/unit/timeouts.test.ts.
 */
export const ANALYZE_TIMEOUT_MS = 290_000;

export type CheckResult<T = AnalyzeResponse> = { ok: true; data: T } | { ok: false; error: CheckError };

export interface CheckParams {
  content: string;
  format: Format;
  showPreferences: boolean;
  /** The article type to check as (S4). Omitted: "auto", the engine's guess from the headings. */
  documentType?: DocumentType | null;
  /** Also ask for the critical reader's brief (a whole-document read; Revise only). */
  review?: boolean;
  /** Also ask for the narrative map (S4b): a whole-document read, sent exactly like the brief. */
  narrative?: boolean;
  /** A reporting checklist to check against (S4): a guideline's id, or "auto". Omitted: none. */
  checklist?: ChecklistChoice | null;
  /**
   * Draft or Revise. The website is the revision studio and always sends
   * "revise", so a Draft choice saved from Word never silently hides the
   * document-wide checks here (Codex review R6).
   */
  mode?: Mode;
  signal?: AbortSignal;
}

/** The S4 options every analysis call carries, always explicit, so a request reads the same from every surface. */
export function analysisOptions(p: {
  showPreferences: boolean;
  documentType?: DocumentType | null;
  review?: boolean;
  narrative?: boolean;
  checklist?: ChecklistChoice | null;
  mode?: Mode;
}): AnalyzeOptions {
  return {
    show_preferences: p.showPreferences,
    document_type: p.documentType ?? "auto",
    review: p.review ?? false,
    narrative: p.narrative ?? false,
    ...(p.checklist ? { checklist: p.checklist } : {}),
    ...(p.mode ? { mode: p.mode } : {}),
  };
}

/**
 * Where a signed-in request gets its token. Implemented over supabase-js in
 * lib/auth.ts; an interface so the retry logic is unit-testable.
 */
export interface EngineAuth {
  /** The current access token (supabase-js refreshes it if it has expired), or null when signed out. */
  token(): Promise<string | null>;
  /**
   * Force a refresh. `token: null` + `transient: true` means it could not be
   * renewed for a passing reason (offline); `transient: false` means the
   * session is dead.
   */
  refresh(): Promise<{ token: string | null; transient?: boolean }>;
  /** Forget the session in this browser (no other device is affected). */
  signOutLocally(): Promise<void>;
}

/**
 * Run an engine call with the caller's bearer token, if any.
 *
 * On 401 `unauthorized` (expired or revoked token): refresh the session once
 * and retry once. If that still fails, sign out locally and say so, rather
 * than silently checking as an anonymous user (s2-design §3).
 */
export async function withBearer<T>(
  auth: EngineAuth | null | undefined,
  attempt: (token: string | null) => Promise<CheckResult<T>>,
): Promise<CheckResult<T>> {
  const token = auth ? await auth.token() : null;
  const first = await attempt(token);
  if (!auth || !token || first.ok || first.error.code !== "unauthorized") return first;

  const fresh = await auth.refresh();
  if (fresh.token) {
    const second = await attempt(fresh.token);
    if (second.ok || second.error.code !== "unauthorized") return second;
  } else if (fresh.transient) {
    return { ok: false, error: refreshUnavailableError() };
  }
  await auth.signOutLocally();
  return { ok: false, error: signedOutError() };
}

export function buildRequest(
  p: Pick<CheckParams, "content" | "format" | "showPreferences" | "documentType" | "review" | "narrative" | "checklist" | "mode">,
): AnalyzeRequest {
  return {
    content: p.content,
    format: p.format,
    options: analysisOptions(p),
  };
}

function authHeader(token: string | null): Record<string, string> {
  return token ? { authorization: `Bearer ${token}` } : {};
}

/** Minimal structural check: enough to render safely, not a full schema validation. */
export function looksLikeAnalyzeResponse(body: unknown): body is AnalyzeResponse {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  return (
    Array.isArray(b.suggestions) &&
    Array.isArray(b.health) &&
    typeof b.hidden_preferences === "number" &&
    Array.isArray(b.sections_detected) &&
    b.suggestions.every(
      (s: unknown) =>
        typeof s === "object" &&
        s !== null &&
        typeof (s as { id?: unknown }).id === "string" &&
        typeof (s as { span?: { start?: unknown } }).span?.start === "number" &&
        typeof (s as { span?: { end?: unknown } }).span?.end === "number",
    )
  );
}

export function looksLikeAnalyzeFileResponse(body: unknown): body is AnalyzeFileResponse {
  if (!looksLikeAnalyzeResponse(body)) return false;
  const d = (body as { document?: unknown }).document;
  if (typeof d !== "object" || d === null) return false;
  const doc = d as Record<string, unknown>;
  return (
    typeof doc.text === "string" &&
    typeof doc.filename === "string" &&
    Array.isArray(doc.segments) &&
    doc.segments.every(
      (g: unknown) =>
        typeof g === "object" &&
        g !== null &&
        typeof (g as { path?: unknown }).path === "string" &&
        typeof (g as { start?: unknown }).start === "number" &&
        typeof (g as { end?: unknown }).end === "number",
    )
  );
}

/** One POST/GET to the engine with the shared timeout, error mapping and shape check. */
async function call<T>(
  url: string,
  init: RequestInit,
  signal: AbortSignal | undefined,
  validate: (body: unknown) => body is T,
  context: { upload?: boolean; engineUrl: string; versioned?: boolean },
): Promise<CheckResult<T>> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), ANALYZE_TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      // No cookies go to the engine; a signed-in caller is identified by the
      // Authorization header only. No referrer either.
      credentials: "omit",
      referrerPolicy: "no-referrer",
      cache: "no-store",
      signal: combined,
    });
  } catch (e) {
    clearTimeout(timer);
    if (signal?.aborted) throw e; // the user cancelled; caller handles it
    return { ok: false, error: networkError(timeout.signal.aborted, context.engineUrl) };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) return { ok: false, error: errorFromResponse(res.status, body, res.headers, { upload: context.upload }) };
  if (!validate(body)) {
    return { ok: false, error: badPayloadError("The engine's answer was not in the expected shape.") };
  }
  const version = (body as { schema_version?: unknown }).schema_version;
  // Analysis responses must say which contract they speak; /v1/rules has no version field.
  if (context.versioned !== false && version !== "1") {
    return {
      ok: false,
      error: badPayloadError(`The engine speaks API version ${String(version)}; this page expects version 1.`),
    };
  }
  return { ok: true, data: body };
}

/** Check pasted text: POST /v1/analyze. */
export async function analyze(
  p: CheckParams,
  engineUrl: string = ENGINE_URL,
  auth?: EngineAuth | null,
): Promise<CheckResult> {
  const body = JSON.stringify(buildRequest(p));
  return withBearer(auth, (token) =>
    call(
      `${engineUrl}/v1/analyze`,
      {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json", ...authHeader(token) },
        body,
      },
      p.signal,
      looksLikeAnalyzeResponse,
      { engineUrl },
    ),
  );
}

export interface FileCheckParams {
  file: File;
  showPreferences: boolean;
  documentType?: DocumentType | null;
  review?: boolean;
  narrative?: boolean;
  checklist?: ChecklistChoice | null;
  mode?: Mode;
  signal?: AbortSignal;
}

/** A header can't carry "Kapitel_ü.docx" as-is: the engine expects encodeURIComponent (contract). */
export function encodeFilename(name: string): string {
  const base = name.replace(/\\/g, "/").split("/").pop()?.trim() || "upload";
  const ext = /\.[A-Za-z0-9]{1,8}$/.exec(base)?.[0] ?? "";
  let encoded: string;
  try {
    encoded = encodeURIComponent(base);
  } catch {
    // A lone surrogate (an unpaired half of an emoji) can't be UTF-8 encoded.
    encoded = encodeURIComponent(`upload${ext}`);
  }
  // The engine uses the name only for its extension; keep the header well
  // under its 1,024-character limit.
  return encoded.length > 600 ? encodeURIComponent(`upload${ext}`) : encoded;
}

/** Everything /v1/analyze-file needs except the transport: unit-tested. */
export function buildFileRequest(
  file: Blob & { name: string },
  opts: Parameters<typeof analysisOptions>[0],
  token: string | null,
): { method: "POST"; headers: Record<string, string>; body: Blob } {
  return {
    method: "POST",
    headers: {
      "content-type": "application/octet-stream",
      accept: "application/json",
      "x-researchly-filename": encodeFilename(file.name),
      "x-researchly-options": JSON.stringify(analysisOptions(opts)),
      ...authHeader(token),
    },
    // The File itself: the browser streams its bytes. Nothing is read into
    // this page's memory, and nothing goes to the Next.js server.
    body: file,
  };
}

/** Check an uploaded file: POST /v1/analyze-file with the raw bytes. */
export async function analyzeFile(
  p: FileCheckParams,
  engineUrl: string = ENGINE_URL,
  auth?: EngineAuth | null,
): Promise<CheckResult<AnalyzeFileResponse>> {
  return withBearer(auth, (token) =>
    call(
      `${engineUrl}/v1/analyze-file`,
      buildFileRequest(
        p.file,
        {
          showPreferences: p.showPreferences,
          documentType: p.documentType,
          review: p.review,
          narrative: p.narrative,
          checklist: p.checklist,
          mode: p.mode,
        },
        token,
      ),
      p.signal,
      looksLikeAnalyzeFileResponse,
      { engineUrl, upload: true },
    ),
  );
}

/** What GET /v1/rules answers: the rules, and (S4) the article types and reporting checklists a caller can choose. */
export interface Registry {
  rules: RuleInfo[];
  /** Empty from an engine older than S4; the surface then falls back to the contract's list. */
  profiles: ProfileChoice[];
  /** Empty from an engine without discipline packs; the surface then falls back to its own list (lib/checklists.ts). */
  checklists: ChecklistChoiceInfo[];
}

function looksLikeRules(body: unknown): body is { rules: RuleInfo[]; profiles?: unknown; checklists?: unknown } {
  const rules = (body as { rules?: unknown } | null)?.rules;
  return (
    Array.isArray(rules) &&
    rules.every((r: unknown) => typeof r === "object" && r !== null && typeof (r as { id?: unknown }).id === "string")
  );
}

function looksLikeProfile(p: unknown): p is ProfileChoice {
  if (typeof p !== "object" || p === null) return false;
  const c = p as Record<string, unknown>;
  return typeof c.id === "string" && typeof c.label === "string" && typeof c.summary === "string";
}

function looksLikeChecklist(c: unknown): c is ChecklistChoiceInfo {
  if (typeof c !== "object" || c === null) return false;
  const x = c as Record<string, unknown>;
  return typeof x.id === "string" && typeof x.label === "string" && typeof x.design === "string" && typeof x.pack === "string";
}

/** The engine's registry: rule names and descriptions, the article types and the checklists. GET /v1/rules; no text is sent. */
export async function listRegistry(engineUrl: string = ENGINE_URL, signal?: AbortSignal): Promise<CheckResult<Registry>> {
  const r = await call(`${engineUrl}/v1/rules`, { method: "GET", headers: { accept: "application/json" } }, signal, looksLikeRules, {
    engineUrl,
    versioned: false,
  });
  if (!r.ok) return r;
  const profiles = Array.isArray(r.data.profiles) ? r.data.profiles.filter(looksLikeProfile) : [];
  const checklists = Array.isArray(r.data.checklists) ? r.data.checklists.filter(looksLikeChecklist) : [];
  return { ok: true, data: { rules: r.data.rules, profiles, checklists } };
}

/** The rule registry (names and one-line descriptions) for the settings page. */
export async function listRules(engineUrl: string = ENGINE_URL, signal?: AbortSignal): Promise<CheckResult<RuleInfo[]>> {
  const r = await listRegistry(engineUrl, signal);
  return r.ok ? { ok: true, data: r.data.rules } : r;
}

/* ---------- the demo manuscript: a public file of this site, not the writer's text ---------- */

/** Where the synthetic demo manuscript is served from (apps/web/public/demo/). */
export const DEMO_MARKDOWN_PATH = "/demo/researchly-demo.md";

/**
 * Fetch the demo manuscript's Markdown from this site's own origin, to load
 * into the editor. A GET of a public static file: nothing is sent, and the
 * text is checked only when the writer presses Check. Here because every
 * network call of the page lives in this file (scripts/check-boundary.mjs).
 */
export async function fetchDemoManuscript(signal?: AbortSignal): Promise<{ ok: true; text: string } | { ok: false }> {
  try {
    const res = await fetch(DEMO_MARKDOWN_PATH, {
      method: "GET",
      headers: { accept: "text/markdown, text/plain" },
      credentials: "omit",
      referrerPolicy: "no-referrer",
      signal,
    });
    if (!res.ok) return { ok: false };
    const text = await res.text();
    return text.trim() ? { ok: true, text } : { ok: false };
  } catch {
    return { ok: false };
  }
}

/* ---------- the Word add-in (S3): /v1/analyze-word and /v1/health ---------- */

export interface WordCheckParams {
  paragraphs: WordParagraph[];
  showPreferences: boolean;
  /** Draft or Revise, always sent: the add-in's toggle decides this check. */
  mode: Mode;
  /** Rules to mute for this request (added to the account's own on the hosted engine). */
  disabledRules?: string[];
  /** The article type to check as (S4); omitted: "auto". */
  documentType?: DocumentType | null;
  /** The critical reader's brief: asked for in Revise, never in Draft (a whole-document read). */
  review?: boolean;
  /** The narrative map (S4b): asked for in Revise only, like the brief. */
  narrative?: boolean;
  /** A reporting checklist (S4): a guideline's id, or "auto"; omitted: none. */
  checklist?: ChecklistChoice | null;
  signal?: AbortSignal;
}

export function buildWordRequest(
  p: Pick<WordCheckParams, "paragraphs" | "showPreferences" | "mode" | "disabledRules" | "documentType" | "review" | "narrative" | "checklist">,
): AnalyzeWordRequest {
  return {
    paragraphs: p.paragraphs,
    options: {
      ...analysisOptions(p),
      disabled_rules: p.disabledRules ?? [],
      mode: p.mode,
    },
  };
}

function isNat(v: unknown): v is number {
  return typeof v === "number" && Number.isInteger(v) && v >= 0;
}

/** Enough to render and to find each suggestion in Word: every card needs a usable location. */
export function looksLikeAnalyzeWordResponse(body: unknown): body is AnalyzeWordResponse {
  if (!looksLikeAnalyzeResponse(body)) return false;
  const b = body as unknown as Record<string, unknown>;
  const cov = b.coverage as Record<string, unknown> | null | undefined;
  if (typeof cov !== "object" || cov === null || !isNat(cov.paragraphs) || !Array.isArray(cov.not_checked)) return false;
  return (b.suggestions as unknown[]).every((s) => {
    const loc = (s as { location?: Record<string, unknown> }).location;
    return (
      typeof loc === "object" &&
      loc !== null &&
      isNat(loc.paragraph) &&
      isNat(loc.start) &&
      isNat(loc.end) &&
      isNat(loc.occurrence) &&
      typeof loc.snippet === "string" &&
      typeof loc.exact === "boolean"
    );
  });
}

/**
 * Check a Word document as its paragraphs: POST /v1/analyze-word.
 *
 * `auth` is null for the "This computer" engine: the local server has no
 * accounts, so the sign-in token never goes there.
 */
export async function analyzeWord(
  p: WordCheckParams,
  engineUrl: string = ENGINE_URL,
  auth?: EngineAuth | null,
): Promise<CheckResult<AnalyzeWordResponse>> {
  const body = JSON.stringify(buildWordRequest(p));
  return withBearer(auth, (token) =>
    call(
      `${engineUrl}/v1/analyze-word`,
      {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json", ...authHeader(token) },
        body,
      },
      p.signal,
      looksLikeAnalyzeWordResponse,
      { engineUrl },
    ),
  );
}

function looksLikeHealth(body: unknown): body is HealthResponse {
  const b = body as { status?: unknown; tiers?: unknown } | null;
  return (
    typeof b === "object" &&
    b !== null &&
    (b.status === "ok" || b.status === "degraded") &&
    Array.isArray(b.tiers) &&
    b.tiers.every((t: unknown) => typeof t === "object" && t !== null && typeof (t as { tier?: unknown }).tier === "string")
  );
}

/** Which tiers the engine is running: GET /v1/health. No text is sent. */
export async function engineHealth(
  engineUrl: string = ENGINE_URL,
  signal?: AbortSignal,
): Promise<CheckResult<HealthResponse>> {
  return call(`${engineUrl}/v1/health`, { method: "GET", headers: { accept: "application/json" } }, signal, looksLikeHealth, {
    engineUrl,
    versioned: false,
  });
}
