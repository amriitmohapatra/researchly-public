import { describe, expect, it } from "vitest";
import type { Suggestion } from "@researchly/contract";
import { markNumbers, numberSuggestions, printedAt, reportTitle } from "@/lib/print";

const sugg = (id: string): Suggestion =>
  ({
    id,
    rule_id: "G101",
    rule_name: "x",
    category: "improvement",
    tier: "craft",
    span: { start: 0, end: 1, line: 1, col: 1 },
    text: "a",
    section: "unknown",
    message: "m",
    why: "w",
    plain: "p",
    source: "s",
    learn_ref: null,
    replacement: null,
    fix_safety: "review",
    confidence: 1,
  }) as Suggestion;

describe("numbers on paper", () => {
  it("numbers the in-text suggestions in order, then the whole-document ones, once each", () => {
    const n = numberSuggestions([sugg("a"), sugg("b"), sugg("a")], [sugg("c")]);
    expect([...n.entries()]).toEqual([
      ["a", 1],
      ["b", 2],
      ["c", 3],
    ]);
  });

  it("a highlight lists the numbers of every suggestion on it, sorted and deduplicated", () => {
    const n = numberSuggestions([sugg("a"), sugg("b"), sugg("c")], []);
    expect(markNumbers({ ids: ["c", "a", "c"] }, n)).toEqual([1, 3]);
    expect(markNumbers({ ids: ["zz"] }, n)).toEqual([]);
  });
});

describe("the report's header", () => {
  it("names the file when there is one, never the text", () => {
    expect(reportTitle(null)).toBe("Researchly check");
    expect(reportTitle({ filename: "chapter2.docx" })).toBe("Researchly check of chapter2.docx");
  });

  it("prints the date in words", () => {
    expect(printedAt(new Date(Date.UTC(2026, 9, 8, 12, 5)), "en-GB")).toMatch(/8 October 2026/);
  });
});
