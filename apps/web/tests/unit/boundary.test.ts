import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { checkBoundary } from "../../scripts/check-boundary.mjs";

const appRoot = path.resolve(__dirname, "../..");

function fixture(files: Record<string, string>): string {
  const root = mkdtempSync(path.join(tmpdir(), "rl-boundary-"));
  const all = { "lib/engine.ts": 'import "client-only";\nexport async function a() { return fetch("x"); }\n', ...files };
  for (const [rel, src] of Object.entries(all)) {
    mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    writeFileSync(path.join(root, rel), src);
  }
  return root;
}

describe("confidentiality boundary (ADR-02): the Next.js app never receives document text", () => {
  it("holds for this app", () => {
    expect(checkBoundary(appRoot)).toEqual([]);
  });

  it("fails on a route handler", () => {
    const root = fixture({ "app/api/analyze/route.ts": "export async function POST(req) { return req.json(); }" });
    expect(checkBoundary(root).join("\n")).toMatch(/route handlers are not allowed/);
  });

  it("fails on a server action", () => {
    const root = fixture({ "app/actions.ts": '"use server";\nexport async function check(text) { return text; }' });
    expect(checkBoundary(root).join("\n")).toMatch(/server actions/);
  });

  it("fails on an inline server action", () => {
    const root = fixture({ "app/page.tsx": 'export default function P() { async function a() { "use server"; } return null; }' });
    expect(checkBoundary(root).join("\n")).toMatch(/server actions/);
  });

  it("fails on a pages/api route", () => {
    const root = fixture({ "pages/api/check.ts": "export default function h() {}" });
    expect(checkBoundary(root).join("\n")).toMatch(/API routes/);
  });

  it("fails when text could be persisted", () => {
    const root = fixture({ "components/X.tsx": "sessionStorage.setItem('doc', text); localStorage.setItem('d', t);" });
    const out = checkBoundary(root).join("\n");
    expect(out).toMatch(/sessionStorage/);
    expect(out).toMatch(/localStorage is only for per-viewer preferences/);
  });

  it("fails on a network call outside lib/engine.ts", () => {
    const root = fixture({ "components/Y.tsx": "fetch('/api/x', { body: text })" });
    expect(checkBoundary(root).join("\n")).toMatch(/lib\/engine\.ts only/);
  });

  it("fails when a proxy reads the request body", () => {
    const root = fixture({ "proxy.ts": "export async function proxy(r) { const b = await r.text(); }" });
    expect(checkBoundary(root).join("\n")).toMatch(/must not read request bodies/);
  });

  it("fails when the engine client is importable from the server", () => {
    const root = fixture({ "lib/engine.ts": "export const x = 1;" });
    expect(checkBoundary(root).join("\n")).toMatch(/client-only/);
  });

  it("S2: supabase-js may be loaded only by lib/supabase.ts, which must be client-only", () => {
    const supa = 'import "client-only";\nexport const c = () => import("@supabase/supabase-js");\n';
    expect(checkBoundary(fixture({ "lib/supabase.ts": supa }))).toEqual([]);
    expect(checkBoundary(fixture({ "lib/supabase.ts": 'export const c = () => import("@supabase/supabase-js");' })).join("\n")).toMatch(
      /lib\/supabase\.ts: must import 'client-only'/,
    );
    const out = checkBoundary(
      fixture({
        "lib/supabase.ts": supa,
        "app/page.tsx": 'import { createClient } from "@supabase/supabase-js";',
        "components/A.tsx": 'const m = await import("@supabase/supabase-js");',
        "components/B.tsx": 'import "@supabase/supabase-js";',
      }),
    ).join("\n");
    expect(out).toMatch(/app\/page\.tsx: supabase-js is loaded only by lib\/supabase\.ts/);
    expect(out).toMatch(/components\/A\.tsx: supabase-js/);
    expect(out).toMatch(/components\/B\.tsx: supabase-js/);
  });

  it("S2: type-only imports are fine anywhere", () => {
    const root = fixture({ "lib/auth.ts": 'import type { Session } from "@supabase/supabase-js";\nexport type S = Session;' });
    expect(checkBoundary(root)).toEqual([]);
  });

  it("S2: refuses the server-side cookie helpers", () => {
    const root = fixture({ "lib/x.ts": 'import type { X } from "@supabase/ssr";' });
    expect(checkBoundary(root).join("\n")).toMatch(/@supabase\/ssr/);
  });

  it("S2: refuses console logging (text and tokens must never reach a log)", () => {
    const root = fixture({ "components/C.tsx": "export const f = (t: string) => console.log(t);" });
    expect(checkBoundary(root).join("\n")).toMatch(/no console logging/);
  });
});
