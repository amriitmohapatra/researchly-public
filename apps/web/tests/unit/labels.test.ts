import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  EMPTY_SESSION,
  EXPORT_FILENAME,
  exportLabels,
  exportText,
  labelContent,
  nextParagraph,
  normaliseSession,
  paragraphsLabelled,
  progressLine,
  setVerdict,
  type LabelSession,
} from "@/lib/labels";

/**
 * The file the Python reader's own test loads too (ml/eval/test_label_precision.py):
 * if either side changes the format, one of the two suites fails.
 */
const FIXTURE = path.resolve(import.meta.dirname, "../../../../ml/eval/fixtures/web-labels.json");

/** Synthetic cards: an id, a rule, a category (what the page passes to setVerdict). */
const card = (id: string, rule_id: string, category: string) => ({ id, rule_id, category });

/** The labelling session the fixture records: two paragraphs, four flags, one changed mind. */
function fixtureSession(): LabelSession {
  let s = EMPTY_SESSION;
  let slots: Record<string, number> = {};
  const step = (c: ReturnType<typeof card>, section: string, v: "useful" | "wrong" | "unsure") => {
    const r = setVerdict(s, slots, c, section, v);
    s = r.session;
    slots = r.slots;
  };
  step(card("a1", "G106", "improvement"), "introduction", "wrong");
  step(card("a1", "G106", "improvement"), "introduction", "useful"); // changed mind: replaced, not added
  step(card("a2", "S001", "correction"), "introduction", "wrong");
  s = nextParagraph(s);
  slots = {};
  step(card("b1", "C201", "convention"), "discussion", "unsure");
  step(card("b2", "C201", "convention"), "discussion", "useful");
  return s;
}

describe("the labels file (S4 exit check)", () => {
  it("is exactly the format ml/eval/label_precision.py reads, and matches the fixture its test loads", () => {
    const s = fixtureSession();
    expect(exportText(s)).toBe(readFileSync(FIXTURE, "utf8"));
    const file = exportLabels(s);
    expect(file.version).toBe(1);
    for (const l of file.labels) expect(Object.keys(l).sort()).toEqual(["category", "paragraph", "rule_id", "section", "verdict"]);
    expect(EXPORT_FILENAME).toBe("researchly-labels.json");
  });

  it("never carries text, even if a stored label had some (a tampered store)", () => {
    const s = normaliseSession({
      paragraph: 2,
      labels: [
        { paragraph: 1, rule_id: "G106", category: "improvement", section: "methods", verdict: "useful", text: "a sentence", snippet: "x" },
        { paragraph: 1, rule_id: "G106", verdict: "maybe" },
        { paragraph: 0, rule_id: "G106", verdict: "useful" },
        { paragraph: 1, rule_id: "a rule id with spaces", verdict: "useful" },
        "not a label",
      ],
    });
    expect(s.labels).toEqual([{ paragraph: 1, rule_id: "G106", category: "improvement", section: "methods", verdict: "useful" }]);
    expect(exportText(s)).not.toContain("sentence");
  });

  it("reads a missing or broken store as empty, and never goes back to an earlier paragraph number", () => {
    expect(normaliseSession(null)).toEqual(EMPTY_SESSION);
    expect(normaliseSession("x")).toEqual(EMPTY_SESSION);
    expect(normaliseSession({ paragraph: -3, labels: "x" })).toEqual(EMPTY_SESSION);
    const s = normaliseSession({ paragraph: 1, labels: [{ paragraph: 4, rule_id: "C201", category: "convention", section: "results", verdict: "wrong" }] });
    expect(s.paragraph).toBe(4);
  });

  it("counts paragraphs and flags for the running line", () => {
    const s = fixtureSession();
    expect(paragraphsLabelled(s)).toBe(2);
    expect(progressLine(s)).toBe("2 of 50 paragraphs, 4 flags labelled");
    expect(progressLine(EMPTY_SESSION)).toBe("0 of 50 paragraphs, 0 flags labelled");
  });

  it("Next paragraph moves on only once the current one has a label", () => {
    expect(nextParagraph(EMPTY_SESSION)).toBe(EMPTY_SESSION);
    const r = setVerdict(EMPTY_SESSION, {}, card("x", "W202", "improvement"), "results", "useful");
    expect(nextParagraph(r.session).paragraph).toBe(2);
  });

  it("sends the section's name as a heading line above the paragraph", () => {
    expect(labelContent("methods", "  We fitted a model.  ")).toBe("Methods\n\nWe fitted a model.\n");
    expect(labelContent("conclusion", "Done.")).toBe("Conclusion\n\nDone.\n");
  });
});
