import { describe, expect, it } from "vitest";
import type { WordParagraph, WordSuggestion } from "@researchly/contract";
import { isHeadingParagraph, sectionAround, sectionName, sectionSummary, sectionView } from "@/lib/word/view";

const P = (text: string, style = "Normal", kind: WordParagraph["kind"] = "body"): WordParagraph => ({ text, style, kind });

/** Synthetic: a title, two headed sections, and a table cell that reads like a heading. */
const DOC: WordParagraph[] = [
  P("A thesis", "Title"),
  P("Some words before any heading."),
  P("Methods", "Heading1"),
  P("First methods paragraph."),
  P("Results", "Heading 1"),
  P("First results paragraph."),
  P("Methods", "Heading1", "table"),
  P("Second results paragraph."),
];

function wsugg(id: string, rule_id: string, paragraph: number): WordSuggestion {
  return {
    id,
    rule_id,
    rule_name: rule_id,
    category: "improvement",
    tier: "craft",
    span: { start: 0, end: 1, line: 1, col: 1 },
    section: "unknown",
    message: "m",
    why: "w",
    plain: "p",
    source: "s",
    text: "t",
    fix_safety: "review",
    confidence: 1,
    location: { paragraph, start: 0, end: 1, snippet: "t", occurrence: 0, exact: true },
  };
}

describe("the section around the cursor", () => {
  it("recognises heading styles by name, never table cells", () => {
    expect(isHeadingParagraph(P("x", "Heading1"))).toBe(true);
    expect(isHeadingParagraph(P("x", "Heading 2"))).toBe(true);
    expect(isHeadingParagraph(P("x", "heading3"))).toBe(true);
    expect(isHeadingParagraph(P("x", "Title"))).toBe(true);
    expect(isHeadingParagraph(P("x", "Normal"))).toBe(false);
    expect(isHeadingParagraph(P("x", "Caption"))).toBe(false);
    expect(isHeadingParagraph(P("x", "Heading1", "table"))).toBe(false);
  });

  it("runs from the nearest heading at or before the cursor to the next heading", () => {
    expect(sectionAround(DOC, 3)).toEqual({ start: 2, end: 4, heading: "Methods" });
    expect(sectionAround(DOC, 2)).toEqual({ start: 2, end: 4, heading: "Methods" }); // the cursor on the heading itself
    expect(sectionAround(DOC, 5)).toEqual({ start: 4, end: 8, heading: "Results" }); // the table cell does not end it
    expect(sectionAround(DOC, 7)).toEqual({ start: 4, end: 8, heading: "Results" });
  });

  it("treats the title as a section of its own, and clamps a cursor outside the document", () => {
    expect(sectionAround(DOC, 1)).toEqual({ start: 0, end: 2, heading: "A thesis" });
    expect(sectionAround(DOC, 99)).toEqual({ start: 4, end: 8, heading: "Results" });
    expect(sectionAround(DOC, -4)).toEqual({ start: 0, end: 2, heading: "A thesis" });
    expect(sectionAround([P("No headings here."), P("At all.")], 1)).toEqual({ start: 0, end: 2, heading: null });
    expect(sectionAround([], 0)).toEqual({ start: 0, end: 0, heading: null });
  });

  it("lists the section's suggestions, keeps document-wide ones aside and counts the rest", () => {
    const list = [wsugg("a", "C120", 3), wsugg("b", "F612", 3), wsugg("c", "C120", 5), wsugg("d", "X101", 7)];
    const focus = sectionAround(DOC, 3);
    const r = sectionView(list, focus, null);
    expect(r.inSection.map((s) => s.id)).toEqual(["a"]);
    expect(r.wholeDocument.map((s) => s.id)).toEqual(["b", "d"]);
    expect(r.elsewhere).toBe(1);
    expect(sectionName(focus)).toBe("“Methods”");
    expect(sectionName({ start: 0, end: 2, heading: null })).toBe("the part before the first heading");
    expect(sectionSummary(r, focus)).toBe("Check complete. 3 suggestions in “Methods”. 1 more elsewhere in the document.");
    expect(sectionSummary({ inSection: [], wholeDocument: [], elsewhere: 0 }, focus)).toBe("Check complete. No suggestions in “Methods”.");
  });
});
