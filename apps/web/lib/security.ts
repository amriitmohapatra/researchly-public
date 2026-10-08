/**
 * Security headers, defined once.
 *
 * - Static headers are applied to every response by next.config.ts.
 * - The Content-Security-Policy needs a fresh nonce per request (Next.js
 *   inlines its bootstrap scripts), so proxy.ts sets it using cspHeader().
 *
 * connect-src is the confidentiality control that matters most: even if a
 * script were injected, the browser could only send data to this origin, to
 * the engine and (in a build with accounts) to the Supabase project.
 */
import { engineOrigin, LOCAL_ENGINE_URL } from "./config";

/* ---------- the Word add-in's taskpane (/word, S3) ---------- */

/** Microsoft's Office JavaScript API, which every Office add-in must load from Microsoft. */
export const OFFICE_JS_URL = "https://appsforoffice.microsoft.com/lib/1/hosted/office.js";
export const OFFICE_JS_ORIGIN = new URL(OFFICE_JS_URL).origin;

/**
 * Where Word on the web frames the taskpane from. Word for Mac and Windows
 * show it in a webview (no framing); Word on the web puts it in an iframe on
 * one of these. Nothing else may frame /word, and nothing may frame any
 * other route.
 */
export const OFFICE_FRAME_ANCESTORS: readonly string[] = [
  "https://*.officeapps.live.com",
  "https://*.office.com",
  "https://*.office365.com",
  "https://*.sharepoint.com",
  "https://*.microsoft365.com",
];

/** The add-in's pages: the route itself and anything beneath it. */
export function isWordPath(pathname: string): boolean {
  return pathname === "/word" || pathname.startsWith("/word/");
}

export interface CspOptions {
  nonce: string;
  engineUrl: string | undefined;
  /** The validated Supabase origin, only when accounts are configured (config.supabaseConfig). */
  supabaseUrl?: string | null;
  dev: boolean;
  /** "word": the add-in taskpane (/word), which Office loads and frames. Default: the site. */
  surface?: "site" | "word";
}

export function cspHeader({ nonce, engineUrl, supabaseUrl, dev, surface = "site" }: CspOptions): string {
  const engine = engineOrigin(engineUrl);
  // Supabase (sign-in and the settings tables) is the only other origin the
  // page may talk to, and only in a build that has accounts (S2).
  const supabase = supabaseUrl ? new URL(supabaseUrl).origin : null;
  const word = surface === "word";
  const connect = ["'self'", engine, ...(supabase && supabase !== engine ? [supabase] : [])];
  // The add-in's "This computer" engine (ADR-02 local mode), and nothing else new.
  if (word && !connect.includes(LOCAL_ENGINE_URL)) connect.push(LOCAL_ENGINE_URL);
  const directives: [string, string[]][] = [
    ["default-src", ["'self'"]],
    [
      "script-src",
      word
        ? // office.js is loaded by a plain <script src> from Microsoft and then
          // loads its host-specific parts from the same origin, sometimes as
          // parser-inserted scripts that 'strict-dynamic' would block. So this
          // route allows exactly that origin, plus this site and the nonce.
          ["'self'", `'nonce-${nonce}'`, OFFICE_JS_ORIGIN, ...(dev ? ["'unsafe-eval'"] : [])]
        : ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(dev ? ["'unsafe-eval'"] : [])],
    ],
    ["style-src", ["'self'", dev ? "'unsafe-inline'" : `'nonce-${nonce}'`]],
    ["img-src", ["'self'", "data:", "blob:"]],
    ["font-src", ["'self'"]],
    ["connect-src", connect],
    ["manifest-src", ["'self'"]],
    ["worker-src", ["'self'"]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'none'"]],
    ["form-action", ["'self'"]],
    ["frame-ancestors", word ? ["'self'", ...OFFICE_FRAME_ANCESTORS] : ["'none'"]],
  ];
  const parts = directives.map(([k, v]) => `${k} ${v.join(" ")}`);
  // Upgrading would turn a local http engine into an unreachable https one;
  // on /word that includes the "This computer" engine, so never there.
  if (!word && !dev && engine.startsWith("https:") && (!supabase || supabase.startsWith("https:"))) {
    parts.push("upgrade-insecure-requests");
  }
  return parts.join("; ");
}

/** Every route except /word: exactly the S1/S2 headers. */
export const STATIC_SECURITY_HEADERS: readonly { key: string; value: string }[] = [
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
  },
];

/**
 * /word: the same, minus X-Frame-Options. It cannot list several origins
 * and DENY would blank the taskpane in Word on the web; the CSP's
 * frame-ancestors (Office origins only) is the framing control there.
 */
export const WORD_SECURITY_HEADERS: readonly { key: string; value: string }[] = STATIC_SECURITY_HEADERS.filter(
  (h) => h.key !== "X-Frame-Options",
);

/** next.config.ts path patterns: /word and below, and everything else. */
export const WORD_SOURCE = "/word/:path*";
export const NOT_WORD_SOURCE = "/:path((?!word$|word/).*)";

/** A nonce for one response: 128 random bits, base64. */
export function makeNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}
