#!/usr/bin/env node
/**
 * The confidentiality boundary, checked as a lint (ADR-02, ARCHITECTURE §5.3):
 * document text goes from the browser straight to the engine and never
 * through this Next.js app.
 *
 * Fails if the app grows anything that could receive text server-side
 * (route handlers, server actions, API routes, a body-reading proxy), sends
 * text from anywhere but lib/engine.ts, persists anything but the format
 * preference, or loads third-party scripts/fonts.
 *
 * S2 (accounts): supabase-js runs in the browser only. It may be loaded only
 * by lib/supabase.ts, which must import 'client-only'; the server-side
 * cookie helpers (@supabase/ssr) are refused; and app code may not log to
 * the console, so neither text nor a token can end up in a log.
 *
 * Usage: node scripts/check-boundary.mjs [appRoot]   (exit 1 on violations)
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SOURCE_EXT = /\.(c|m)?(t|j)sx?$/;
/** The only files that may touch localStorage: per-viewer choices, never text. */
const PREF_FILES = new Set(["lib/prefs.ts", "lib/results-prefs.ts"]);
const SKIP_DIRS = new Set(["node_modules", ".next", "out", "test-results", "playwright-report", "tests", "e2e", "scripts"]);

function walk(dir, root, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of entries) {
    // .next, and the e2e suite's second build output (.next-accounts).
    if (SKIP_DIRS.has(name) || name.startsWith(".next")) continue;
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, root, out);
    else if (SOURCE_EXT.test(name)) out.push(path.relative(root, full).split(path.sep).join("/"));
  }
  return out;
}

/** Strip comments so prose that *mentions* an API does not trip the check. */
function code(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

/** A runtime (non-type) import, dynamic import or require of supabase-js. */
function valueImportsSupabase(src) {
  const pkg = String.raw`["']@supabase\/[\w-]+(\/[\w./-]*)?["']`;
  const staticImport = new RegExp(String.raw`(^|[\n;])\s*import\s+(?!type\b)[^;]*?from\s*${pkg}|(^|[\n;])\s*import\s*${pkg}`);
  const reexport = new RegExp(String.raw`(^|[\n;])\s*export\s+(?!type\b)[^;]*?from\s*${pkg}`);
  const dynamic = new RegExp(String.raw`\b(import|require)\s*\(\s*${pkg}`);
  return staticImport.test(src) || reexport.test(src) || dynamic.test(src);
}

export function checkBoundary(root) {
  const files = walk(root, root).filter((f) => !/(^|\/)(next\.config|vitest\.config|playwright\.config|eslint\.config)\./.test(f));
  const problems = [];
  const flag = (file, msg) => problems.push(`${file}: ${msg}`);

  for (const f of files) {
    const src = code(readFileSync(path.join(root, f), "utf8"));

    if (/(^|\/)app\/.*\/?route\.(c|m)?(t|j)sx?$/.test(f) || /^(src\/)?app\/route\./.test(f)) {
      flag(f, "route handlers are not allowed: the web app must never receive document text");
    }
    if (/^(src\/)?pages\/api\//.test(f)) flag(f, "API routes are not allowed: the web app must never receive document text");
    if (/(^|[\s;{(])["']use server["']/.test(src)) {
      flag(f, "server actions ('use server') are not allowed: they would send text to the Next.js server");
    }
    if (/\bfetch\s*\(/.test(src) && f !== "lib/engine.ts") {
      flag(f, "network calls belong in lib/engine.ts only (the single, audited path to the engine)");
    }
    if (/\b(XMLHttpRequest|sendBeacon|WebSocket|EventSource)\b/.test(src)) {
      flag(f, "XMLHttpRequest/sendBeacon/WebSocket/EventSource are not allowed; use lib/engine.ts");
    }
    if (/\b(sessionStorage|indexedDB|document\.cookie|cookies\s*\()/.test(src)) {
      flag(f, "no sessionStorage, IndexedDB or cookies in S1: the document is never persisted");
    }
    if (/\blocalStorage\b/.test(src) && !PREF_FILES.has(f)) {
      flag(
        f,
        "localStorage is only for per-viewer preferences (format; the Word add-in's engine and Draft/Revise; the reporting checklist), in lib/prefs.ts or lib/results-prefs.ts",
      );
    }
    if (/dangerouslySetInnerHTML|\binnerHTML\b|insertAdjacentHTML/.test(src)) {
      flag(f, "never render HTML from data; document text is rendered as text");
    }
    if (/from\s+["']next\/script["']|from\s+["']next\/font\/google["']/.test(src)) {
      flag(f, "no third-party scripts or font CDNs");
    }
    if (/^(src\/)?(proxy|middleware)\.(t|j)s$/.test(f) && /\.(body|json|text|formData|arrayBuffer|blob)\s*(\(|\b)/.test(src.replace(/\.headers\b/g, ""))) {
      flag(f, "the proxy must not read request bodies");
    }
    // S2 accounts: Supabase lives in the browser only. The server-side
    // helpers would put sessions in cookies the Next.js server reads.
    if (/["']@supabase\/(ssr|auth-helpers[\w-]*)["']/.test(src)) {
      flag(f, "@supabase/ssr and auth-helpers are not allowed: sessions stay in the browser, never in server-read cookies");
    }
    if (f !== "lib/supabase.ts" && valueImportsSupabase(src)) {
      flag(f, "supabase-js is loaded only by lib/supabase.ts (client-only); import types with `import type` elsewhere");
    }
    // Text and tokens must never reach a log the user did not ask for.
    if (/\bconsole\s*\.\s*(log|info|debug|warn|error|trace|dir|table)\s*\(/.test(src)) {
      flag(f, "no console logging in app code: document text and sign-in tokens must never reach a log");
    }
  }

  for (const required of ["lib/engine.ts", "lib/supabase.ts"]) {
    if (required === "lib/supabase.ts" && !files.includes(required)) continue; // a build without accounts code
    const src = files.includes(required) ? readFileSync(path.join(root, required), "utf8") : "";
    if (!/import\s+["']client-only["']/.test(src)) {
      problems.push(
        required === "lib/engine.ts"
          ? "lib/engine.ts: must import 'client-only' so server code can never import the text-sending path"
          : "lib/supabase.ts: must import 'client-only' so server code can never load supabase-js or see a session",
      );
    }
  }
  return problems;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));
  const problems = checkBoundary(root);
  if (problems.length) {
    console.error(`Confidentiality boundary check failed (${problems.length}):`);
    for (const p of problems) console.error(`  - ${p}`);
    process.exit(1);
  }
  console.log("Confidentiality boundary check passed: no route handlers, server actions or text persistence.");
}
