/**
 * Public build-time configuration. Every NEXT_PUBLIC_* value is inlined into
 * the browser bundle, so the browser (never a Next.js server route) calls the
 * engine and Supabase directly (ADR-02, §5.3, docs/s2-design.md §5).
 *
 * A malformed value fails the build (next.config.ts calls these validators)
 * rather than shipping a page whose every request fails.
 */
export const DEFAULT_ENGINE_URL = "http://localhost:8080";

/** Normalises an engine base URL: absolute http(s), no trailing slash, no path quirks. */
export function normaliseEngineUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim() || DEFAULT_ENGINE_URL;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NEXT_PUBLIC_ENGINE_URL is not a valid absolute URL: ${JSON.stringify(value)}`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`NEXT_PUBLIC_ENGINE_URL must be http(s), got ${url.protocol}`);
  }
  return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
}

/** The origin only — what the Content-Security-Policy's connect-src allows. */
export function engineOrigin(raw: string | undefined): string {
  return new URL(normaliseEngineUrl(raw)).origin;
}

export const ENGINE_URL = normaliseEngineUrl(process.env.NEXT_PUBLIC_ENGINE_URL);

/**
 * The Word add-in's "This computer" engine (ADR-02 local mode): the add-in's
 * own server.py on the writer's machine. Fixed, so the CSP can name it.
 */
export const LOCAL_ENGINE_URL = "http://localhost:3517";

/* ---------- reporting a problem ---------- */

/** Every issue report goes to the owner's inbox (owner's request, S3). */
export const SUPPORT_EMAIL = "amrit.mohapatra97@gmail.com";

/** A mailto: link with a short subject. Never prefilled with any document text. */
export function reportProblemHref(subject: string): string {
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}`;
}

/* ---------- accounts (Supabase), S2 ---------- */

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
/** A Supabase project host: one project-ref label under supabase.co. */
const SUPABASE_HOST = /^[a-z0-9-]+\.supabase\.co$/;

/**
 * Validates NEXT_PUBLIC_SUPABASE_URL and returns its origin, or null when unset.
 *
 * Only a hosted project (`https://<ref>.supabase.co`) or a local Supabase
 * (`http(s)://localhost:<port>`, the CLI's dev stack) is accepted: this origin
 * is added to the CSP's connect-src, so a typo must not widen it to anywhere.
 */
export function normaliseSupabaseUrl(raw: string | undefined): string | null {
  const value = (raw ?? "").trim();
  if (!value) return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NEXT_PUBLIC_SUPABASE_URL is not a valid absolute URL: ${JSON.stringify(value)}`);
  }
  const local = LOCAL_HOSTS.has(url.hostname);
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    throw new Error(`NEXT_PUBLIC_SUPABASE_URL must be https (http only for localhost), got ${url.protocol}`);
  }
  if (!local && !SUPABASE_HOST.test(url.hostname)) {
    throw new Error(
      `NEXT_PUBLIC_SUPABASE_URL must be a Supabase project URL (https://<project>.supabase.co) or localhost, got ${url.hostname}`,
    );
  }
  if (url.username || url.password || url.search || url.hash || url.pathname.replace(/\/+$/, "") !== "") {
    throw new Error("NEXT_PUBLIC_SUPABASE_URL must be the project's base URL, with no path, query or credentials");
  }
  return url.origin;
}

/**
 * Validates NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, or returns null when unset.
 * The publishable key is public by design (RLS protects the data). A secret
 * key must never reach the browser bundle, so one is refused loudly.
 */
export function normaliseSupabaseKey(raw: string | undefined): string | null {
  const value = (raw ?? "").trim();
  if (!value) return null;
  if (value.startsWith("sb_secret_")) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY holds a SECRET key (sb_secret_…). It would be published to every visitor. Use the publishable key (sb_publishable_…) and rotate the secret one.",
    );
  }
  if (!/^sb_publishable_[A-Za-z0-9_-]{8,}$/.test(value)) {
    throw new Error("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY must be a Supabase publishable key (sb_publishable_…)");
  }
  return value;
}

export interface SupabaseConfig {
  url: string;
  key: string;
}

/**
 * Accounts are on only when both values are set. With either unset the site
 * is the S1 site: no sign-in UI, no upload, no Supabase code loaded. A value
 * that is set but malformed still throws, so a half-done setup is noticed.
 */
export function supabaseConfig(rawUrl: string | undefined, rawKey: string | undefined): SupabaseConfig | null {
  const url = normaliseSupabaseUrl(rawUrl);
  const key = normaliseSupabaseKey(rawKey);
  return url && key ? { url, key } : null;
}

export const SUPABASE = supabaseConfig(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
);

/** Whether this build has accounts (sign-in, uploads, synced settings). */
export const ACCOUNTS_ENABLED = SUPABASE !== null;
