import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadChecklistSetting, saveChecklistSetting, subscribeChecklistSetting } from "@/lib/results-prefs";
import { checkBoundary } from "../../scripts/check-boundary.mjs";

function fakeStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, v),
    keys: () => [...m.keys()],
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("the remembered reporting checklist", () => {
  it("round-trips a valid choice under its own key, and nothing else", () => {
    const storage = fakeStorage();
    vi.stubGlobal("window", { localStorage: storage });
    expect(loadChecklistSetting()).toBeNull();
    saveChecklistSetting("epiforge");
    expect(storage.keys()).toEqual(["researchly.checklist"]);
    expect(loadChecklistSetting()).toBe("epiforge");
    saveChecklistSetting("none");
    expect(loadChecklistSetting()).toBe("none");
  });

  it("ignores a value it does not know", () => {
    const storage = fakeStorage();
    storage.setItem("researchly.checklist", "<script>");
    vi.stubGlobal("window", { localStorage: storage });
    expect(loadChecklistSetting()).toBeNull();
  });

  it("survives blocked storage: nothing is remembered and nothing throws", () => {
    const blocked = {
      get localStorage(): Storage {
        throw new Error("SecurityError");
      },
    };
    vi.stubGlobal("window", blocked);
    expect(loadChecklistSetting()).toBeNull();
    expect(() => saveChecklistSetting("strobe")).not.toThrow();
  });

  it("follows another tab's change of this key only", () => {
    const listeners: ((e: { key: string }) => void)[] = [];
    vi.stubGlobal("window", {
      addEventListener: (_t: string, fn: (e: { key: string }) => void) => listeners.push(fn),
      removeEventListener: () => undefined,
    });
    let n = 0;
    const off = subscribeChecklistSetting(() => n++);
    listeners[0]!({ key: "researchly.format" });
    listeners[0]!({ key: "researchly.checklist" });
    expect(n).toBe(1);
    off();
  });
});

describe("the boundary allows storage in the two preference files only", () => {
  it("lets lib/results-prefs.ts use localStorage and still refuses it elsewhere", () => {
    const root = mkdtempSync(path.join(tmpdir(), "rl-prefs-"));
    const files: Record<string, string> = {
      "lib/engine.ts": 'import "client-only";\nexport const a = 1;\n',
      "lib/results-prefs.ts": "export const v = () => localStorage.getItem('researchly.checklist');",
      "components/Other.tsx": "export const v = () => localStorage.getItem('x');",
    };
    for (const [rel, src] of Object.entries(files)) {
      mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
      writeFileSync(path.join(root, rel), src);
    }
    const problems = checkBoundary(root);
    expect(problems.some((p: string) => p.startsWith("lib/results-prefs.ts"))).toBe(false);
    expect(problems.some((p: string) => p.startsWith("components/Other.tsx") && /localStorage/.test(p))).toBe(true);
  });
});
