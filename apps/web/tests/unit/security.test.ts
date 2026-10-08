import { describe, expect, it } from "vitest";
import { engineOrigin, normaliseEngineUrl } from "@/lib/config";
import {
  cspHeader,
  isWordPath,
  makeNonce,
  NOT_WORD_SOURCE,
  OFFICE_FRAME_ANCESTORS,
  OFFICE_JS_ORIGIN,
  OFFICE_JS_URL,
  STATIC_SECURITY_HEADERS,
  WORD_SECURITY_HEADERS,
  WORD_SOURCE,
} from "@/lib/security";

const directive = (csp: string, name: string) =>
  csp
    .split(";")
    .map((d) => d.trim())
    .find((d) => d.startsWith(`${name} `));

describe("engine URL", () => {
  it("defaults to localhost:8080 and strips trailing slashes", () => {
    expect(normaliseEngineUrl(undefined)).toBe("http://localhost:8080");
    expect(normaliseEngineUrl("https://engine.example.org/")).toBe("https://engine.example.org");
    expect(normaliseEngineUrl("https://x.example/api//")).toBe("https://x.example/api");
  });
  it("rejects non-http URLs", () => {
    expect(() => normaliseEngineUrl("javascript:alert(1)")).toThrow();
    expect(() => normaliseEngineUrl("not a url")).toThrow();
  });
  it("reduces to an origin for the CSP", () => {
    expect(engineOrigin("https://engine.example.org/base/")).toBe("https://engine.example.org");
  });
});

describe("Content-Security-Policy", () => {
  const csp = cspHeader({ nonce: "abc123", engineUrl: "https://engine.example.org", dev: false });

  it("lets the page connect only to itself and the engine origin", () => {
    expect(directive(csp, "connect-src")).toBe("connect-src 'self' https://engine.example.org");
  });
  it("allows scripts only by nonce, with no unsafe-inline or unsafe-eval in production", () => {
    const s = directive(csp, "script-src")!;
    expect(s).toContain("'nonce-abc123'");
    expect(s).toContain("'strict-dynamic'");
    expect(s).not.toContain("unsafe");
    expect(directive(csp, "style-src")).not.toContain("unsafe");
  });
  it("forbids framing, plugins and base-tag hijacking", () => {
    expect(directive(csp, "frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(directive(csp, "object-src")).toBe("object-src 'none'");
    expect(directive(csp, "base-uri")).toBe("base-uri 'none'");
  });
  it("upgrades insecure requests only when the engine is https", () => {
    expect(csp).toContain("upgrade-insecure-requests");
    expect(cspHeader({ nonce: "n", engineUrl: "http://localhost:8080", dev: false })).not.toContain("upgrade-insecure-requests");
  });
  it("allows eval only in development", () => {
    expect(cspHeader({ nonce: "n", engineUrl: undefined, dev: true })).toContain("'unsafe-eval'");
  });
  it("has no external font or script hosts at all", () => {
    expect(csp).not.toMatch(/fonts\.googleapis|gstatic|googletagmanager|cdn\./);
  });
});

describe("Content-Security-Policy with accounts (S2)", () => {
  it("adds exactly the Supabase origin to connect-src, and nothing else changes", () => {
    const base = cspHeader({ nonce: "n", engineUrl: "https://engine.example.org", dev: false });
    const csp = cspHeader({
      nonce: "n",
      engineUrl: "https://engine.example.org",
      supabaseUrl: "https://abcdefghij.supabase.co",
      dev: false,
    });
    expect(directive(csp, "connect-src")).toBe("connect-src 'self' https://engine.example.org https://abcdefghij.supabase.co");
    const others = (s: string) => s.split(";").filter((d) => !d.trim().startsWith("connect-src")).join(";");
    expect(others(csp)).toBe(others(base));
  });
  it("leaves connect-src as in S1 without accounts", () => {
    for (const supabaseUrl of [undefined, null]) {
      const csp = cspHeader({ nonce: "n", engineUrl: "https://engine.example.org", supabaseUrl, dev: false });
      expect(directive(csp, "connect-src")).toBe("connect-src 'self' https://engine.example.org");
    }
  });
  it("does not upgrade requests to a local http Supabase", () => {
    const csp = cspHeader({ nonce: "n", engineUrl: "https://e.example.org", supabaseUrl: "http://localhost:54321", dev: false });
    expect(csp).not.toContain("upgrade-insecure-requests");
  });
});

describe("static headers and nonces", () => {
  it("sends no referrer and no sniffing", () => {
    const h = Object.fromEntries(STATIC_SECURITY_HEADERS.map((x) => [x.key, x.value]));
    expect(h["Referrer-Policy"]).toBe("no-referrer");
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["X-Frame-Options"]).toBe("DENY");
  });
  it("makes fresh, 128-bit base64 nonces", () => {
    const a = makeNonce();
    expect(a).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    expect(makeNonce()).not.toBe(a);
  });
});

describe("the Word taskpane's headers (/word, S3)", () => {
  const site = cspHeader({ nonce: "n", engineUrl: "https://engine.example.org", supabaseUrl: "https://abcdefghij.supabase.co", dev: false });
  const word = cspHeader({
    nonce: "n",
    engineUrl: "https://engine.example.org",
    supabaseUrl: "https://abcdefghij.supabase.co",
    dev: false,
    surface: "word",
  });

  it("matches /word and below only", () => {
    expect(isWordPath("/word")).toBe(true);
    expect(isWordPath("/word/icon-32.png")).toBe(true);
    for (const p of ["/", "/settings", "/wordy", "/words/x", "/a/word"]) expect(isWordPath(p)).toBe(false);
  });

  it("lets Word on the web frame it, and nothing else", () => {
    expect(directive(word, "frame-ancestors")).toBe(`frame-ancestors 'self' ${OFFICE_FRAME_ANCESTORS.join(" ")}`);
    for (const o of OFFICE_FRAME_ANCESTORS) expect(o).toMatch(/^https:\/\/\*\.[a-z0-9.]+$/);
  });

  it("allows exactly Microsoft's office.js origin for scripts, without unsafe-inline", () => {
    const s = directive(word, "script-src")!;
    expect(s).toBe(`script-src 'self' 'nonce-n' ${OFFICE_JS_ORIGIN}`);
    expect(OFFICE_JS_URL).toBe("https://appsforoffice.microsoft.com/lib/1/hosted/office.js");
    expect(s).not.toContain("unsafe");
  });

  it("connects only to itself, the engine, Supabase and the local engine on port 3517", () => {
    expect(directive(word, "connect-src")).toBe(
      "connect-src 'self' https://engine.example.org https://abcdefghij.supabase.co http://localhost:3517",
    );
    // Upgrading would turn http://localhost:3517 into an unreachable https URL.
    expect(word).not.toContain("upgrade-insecure-requests");
  });

  it("changes nothing else, and leaves every other route exactly as before", () => {
    const rest = (s: string) =>
      s
        .split(";")
        .map((d) => d.trim())
        .filter((d) => !/^(script-src|connect-src|frame-ancestors|upgrade-insecure-requests)\b/.test(d))
        .join("; ");
    expect(rest(word)).toBe(rest(site));
    expect(site).toBe(
      cspHeader({ nonce: "n", engineUrl: "https://engine.example.org", supabaseUrl: "https://abcdefghij.supabase.co", dev: false, surface: "site" }),
    );
    expect(directive(site, "frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(site).not.toContain("appsforoffice");
    expect(site).not.toContain("3517");
  });

  it("drops only X-Frame-Options on /word; every other route keeps DENY", () => {
    expect(WORD_SECURITY_HEADERS.map((h) => h.key)).toEqual(
      STATIC_SECURITY_HEADERS.map((h) => h.key).filter((k) => k !== "X-Frame-Options"),
    );
    expect(STATIC_SECURITY_HEADERS.find((h) => h.key === "X-Frame-Options")?.value).toBe("DENY");
    expect(WORD_SOURCE).toBe("/word/:path*");
    // The pattern next.config.ts applies the full set to: everything but /word and below.
    const notWord = new RegExp(`^/${NOT_WORD_SOURCE.slice("/:path".length)}$`);
    for (const p of ["/", "/settings", "/wordy", "/_next/static/x.js", "/icon.svg"]) expect(notWord.test(p), p).toBe(true);
    for (const p of ["/word", "/word/icon-32.png"]) expect(notWord.test(p), p).toBe(false);
  });
});
