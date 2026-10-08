import type { Category, Suggestion } from "@researchly/contract";

/** A contract-valid Suggestion with overridable fields. */
export function sugg(
  id: string,
  start: number,
  end: number,
  category: Category = "improvement",
  extra: Partial<Suggestion> = {},
): Suggestion {
  return {
    id,
    rule_id: "T001",
    rule_name: "Test rule",
    category,
    tier: "craft",
    span: { start, end, line: 1, col: start + 1 },
    section: "unknown",
    message: "m",
    why: "w",
    plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    source: "s",
    text: "",
    fix_safety: "review",
    confidence: 1,
    ...extra,
  };
}

/** Independent reference implementation: Python-style slicing by code point. */
export function pySlice(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join("");
}

/** Python-style index of `needle` in `text`, in code points. */
export function pyIndex(text: string, needle: string): number {
  const i = text.indexOf(needle);
  if (i < 0) throw new Error(`needle not found: ${needle}`);
  return Array.from(text.slice(0, i)).length;
}
