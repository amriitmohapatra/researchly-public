import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadDocumentTypeChoice, loadFormat, loadModeChoice, saveDocumentTypeChoice } from "@/lib/prefs";

/** A window with just enough localStorage for prefs.ts; the unit suite runs without a DOM. */
function fakeWindow(store: Map<string, string>) {
  return {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
    },
    addEventListener() {},
    removeEventListener() {},
  };
}

describe("the article-type preference (S4)", () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    store.clear();
    vi.stubGlobal("window", fakeWindow(store));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("round-trips a known type under its own key, touching nothing else", () => {
    expect(loadDocumentTypeChoice()).toBeNull();
    saveDocumentTypeChoice("thesis-chapter");
    expect(loadDocumentTypeChoice()).toBe("thesis-chapter");
    expect([...store.keys()]).toEqual(["researchly.document-type"]);
    expect(loadFormat()).toBeNull();
    expect(loadModeChoice()).toBeNull();
  });

  it("ignores a stored value that is not an article type (a tampered or older store)", () => {
    store.set("researchly.document-type", "poem");
    expect(loadDocumentTypeChoice()).toBeNull();
    store.set("researchly.document-type", "");
    expect(loadDocumentTypeChoice()).toBeNull();
  });

  it("survives storage that throws (private mode): no choice, no crash", () => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem() {
          throw new Error("blocked");
        },
        setItem() {
          throw new Error("blocked");
        },
      },
    });
    expect(loadDocumentTypeChoice()).toBeNull();
    expect(() => saveDocumentTypeChoice("grant")).not.toThrow();
  });
});
