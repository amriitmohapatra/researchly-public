import { describe, expect, it } from "vitest";
import type { AnalyzeResponse, Suggestion } from "@researchly/contract";
import {
  applyFilter,
  applySectionFilter,
  countBySection,
  dismissedCount,
  heldBackSentence,
  hiddenPreferenceCount,
  revealNeedsRecheck,
  shownSuggestions,
  summarySentence,
  withoutSetAside,
} from "@/lib/view";
import { sugg } from "./helpers";

function response(suggestions: Suggestion[], hidden_preferences = 0): AnalyzeResponse {
  return {
    schema_version: "1",
    signed_in: false,
    warnings: [],
    suggestions,
    counts: {},
    hidden_preferences,
    sections_detected: [],
    health: [],
    engine: { service_version: "0", core_version: "0", rules_loaded: 0 },
    elapsed_ms: 1,
    mode: "revise",
    hidden_by_mode: 0,
  };
}

describe("view model", () => {
  const list = [
    sugg("p", 0, 3, "preference"),
    sugg("c2", 10, 12, "correction"),
    sugg("i", 4, 8, "improvement"),
    sugg("c1", 4, 6, "correction"),
  ];

  it("hides preferences unless asked, and sorts by position then importance", () => {
    expect(shownSuggestions(response(list), false).map((s) => s.id)).toEqual(["c1", "i", "c2"]);
    expect(shownSuggestions(response(list), true).map((s) => s.id)).toEqual(["p", "c1", "i", "c2"]);
  });

  it("counts hidden preferences from the engine and from the toggle", () => {
    expect(hiddenPreferenceCount(response(list, 0), false)).toBe(1);
    expect(hiddenPreferenceCount(response(list, 0), true)).toBe(0);
    expect(hiddenPreferenceCount(response([], 4), false)).toBe(4);
    expect(hiddenPreferenceCount(response([], 4), true)).toBe(4); // still needs a re-check
  });

  it("knows when revealing preferences needs a fresh request", () => {
    expect(revealNeedsRecheck(response([], 3))).toBe(true);
    expect(revealNeedsRecheck(response(list, 0))).toBe(false);
  });

  it("filters by category", () => {
    expect(applyFilter(list, "correction").map((s) => s.id)).toEqual(["c2", "c1"]);
    expect(applyFilter(list, "all")).toHaveLength(4);
  });

  it("announces a summary without any score", () => {
    expect(summarySentence([])).toBe("Check complete. No suggestions.");
    const s = summarySentence(shownSuggestions(response(list), false));
    expect(s).toBe("Check complete. 3 suggestions: 2 corrections, 1 improvement.");
    expect(s).not.toMatch(/score|grade|%/i);
  });
});

describe("section view", () => {
  const list = [
    sugg("m1", 0, 2, "improvement", { section: "methods", rule_id: "C120" }),
    sugg("m2", 3, 5, "convention", { section: "methods", rule_id: "F612" }),
    sugg("d1", 6, 8, "improvement", { section: "discussion", rule_id: "C120" }),
    sugg("d2", 9, 11, "convention", { section: "discussion", rule_id: "X101" }),
    sugg("u1", 12, 13, "correction", { section: "unknown", rule_id: "S010" }),
  ];

  it("counts shown suggestions per section", () => {
    expect(countBySection(list)).toEqual({ methods: 2, discussion: 2, unknown: 1 });
  });

  it("'all' lists everything in one group", () => {
    const r = applySectionFilter(list, "all", null);
    expect(r.inSection).toHaveLength(5);
    expect(r.wholeDocument).toEqual([]);
    expect(r.elsewhere).toBe(0);
  });

  it("a section keeps its sentence-level suggestions and the document-wide ones, wherever they are", () => {
    const r = applySectionFilter(list, "methods", null);
    expect(r.inSection.map((s) => s.id)).toEqual(["m1"]);
    expect(r.wholeDocument.map((s) => s.id)).toEqual(["m2", "d2"]);
    expect(r.elsewhere).toBe(2);
  });
});

describe("set aside in this check: dismissed once, muted just now (review proposal 2)", () => {
  const list = [sugg("a", 0, 2), sugg("b", 3, 5, "improvement", { rule_id: "G101" }), sugg("c", 6, 8, "correction", { rule_id: "G101" }), sugg("d", 9, 10)];

  it("leaves out dismissed suggestions and every suggestion of a muted rule, in order", () => {
    expect(withoutSetAside(list, new Set()).map((s) => s.id)).toEqual(["a", "b", "c", "d"]);
    expect(withoutSetAside(list, new Set(["a"])).map((s) => s.id)).toEqual(["b", "c", "d"]);
    expect(withoutSetAside(list, new Set(["d"]), new Set(["G101"])).map((s) => s.id)).toEqual(["a"]);
  });

  it("counts only the dismissed ones still on show (a muted rule's are gone anyway)", () => {
    expect(dismissedCount(list, new Set())).toBe(0);
    expect(dismissedCount(list, new Set(["a", "b", "zz"]))).toBe(2);
    expect(dismissedCount(list, new Set(["a", "b"]), new Set(["G101"]))).toBe(1);
  });
});

describe("what Draft held back (review R6)", () => {
  it("is said in one line, and not at all in Revise", () => {
    expect(heldBackSentence(0)).toBeNull();
    expect(heldBackSentence(-1)).toBeNull();
    expect(heldBackSentence(Number.NaN)).toBeNull();
    expect(heldBackSentence(1)).toBe("Draft mode held back 1 whole-document suggestion.");
    expect(heldBackSentence(1200)).toBe("Draft mode held back 1,200 whole-document suggestions.");
  });
});
