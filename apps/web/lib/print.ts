/**
 * The printable report (S4, owner request 2026-10-08): one check on paper,
 * or as a PDF through the browser's own "Save as PDF". Made entirely in the
 * browser: no document text leaves the page for it (ADR-02).
 *
 * On paper a highlight cannot be clicked, so every highlighted stretch
 * carries a number and the suggestions are listed under the same numbers,
 * in document order, beside the text. Pure helpers here; unit-tested.
 */
import type { Suggestion } from "@researchly/contract";
import type { Segment } from "./segments";

/** Suggestion id -> its number on paper, in document order (whole-document checks last). */
export function numberSuggestions(inSection: readonly Suggestion[], wholeDocument: readonly Suggestion[]): Map<string, number> {
  const out = new Map<string, number>();
  let n = 1;
  for (const s of inSection) if (!out.has(s.id)) out.set(s.id, n++);
  for (const s of wholeDocument) if (!out.has(s.id)) out.set(s.id, n++);
  return out;
}

/** The numbers a highlighted stretch refers to, in order, deduplicated ("1, 3"). */
export function markNumbers(segment: Pick<Segment, "ids">, numbers: ReadonlyMap<string, number>): number[] {
  const seen = new Set<number>();
  for (const id of segment.ids) {
    const n = numbers.get(id);
    if (n !== undefined) seen.add(n);
  }
  return [...seen].sort((a, b) => a - b);
}

/** "8 October 2026, 14:05", in the reader's locale; the only date on the page. */
export function printedAt(now: Date = new Date(), locale: string | undefined = undefined): string {
  return new Intl.DateTimeFormat(locale ?? "en-GB", { dateStyle: "long", timeStyle: "short" }).format(now);
}

/** The title line: where the text came from. Never the text itself. */
export function reportTitle(source: { filename: string } | null | undefined): string {
  return source?.filename ? `Researchly check of ${source.filename}` : "Researchly check";
}
