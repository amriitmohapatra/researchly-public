/** Pure view-model helpers for the results screen (unit-tested). */
import type { AnalyzeResponse, Category, Suggestion } from "@researchly/contract";
import { CATEGORIES, CATEGORY_ORDER, countByCategory } from "./categories";
import { splitForSection, type ScopeMap, type SectionSplit } from "./scope";

export type Filter = Category | "all";
/** The section chooser: everything, or one entry of `sections_detected`. */
export type SectionFilter = "all" | string;

/** Preferences are hidden unless the writer asked for them (CLAUDE.md #3). */
export function shownSuggestions(data: AnalyzeResponse, showPreferences: boolean): Suggestion[] {
  const list = showPreferences ? data.suggestions : data.suggestions.filter((s) => s.category !== "preference");
  return [...list].sort(
    (a, b) =>
      a.span.start - b.span.start ||
      CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) ||
      a.span.end - b.span.end ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
}

/**
 * Preferences the writer is not seeing: those the engine withheld, plus any
 * it returned that the toggle now hides client-side.
 */
export function hiddenPreferenceCount(data: AnalyzeResponse, showPreferences: boolean): number {
  const returned = data.suggestions.filter((s) => s.category === "preference").length;
  return data.hidden_preferences + (showPreferences ? 0 : returned);
}

/** Whether revealing the hidden preferences needs another request (the engine withheld them). */
export function revealNeedsRecheck(data: AnalyzeResponse): boolean {
  return data.hidden_preferences > 0;
}

/**
 * Leave out what the writer set aside in this check: suggestions dismissed
 * once ("Not an issue here", session only) and rules just muted (filtered
 * at once, before the re-check confirms it).
 */
export function withoutSetAside(
  list: readonly Suggestion[],
  dismissed: ReadonlySet<string>,
  mutedRules: ReadonlySet<string> = new Set(),
): Suggestion[] {
  if (dismissed.size === 0 && mutedRules.size === 0) return [...list];
  return list.filter((s) => !dismissed.has(s.id) && !mutedRules.has(s.rule_id));
}

/** How many of `dismissed` are still among the suggestions shown (a toggle or a mute can hide some anyway). */
export function dismissedCount(list: readonly Suggestion[], dismissed: ReadonlySet<string>, mutedRules: ReadonlySet<string> = new Set()): number {
  if (dismissed.size === 0) return 0;
  return list.filter((s) => dismissed.has(s.id) && !mutedRules.has(s.rule_id)).length;
}

/**
 * What Draft mode held back, in one line (Codex review R6). The website
 * asks for Revise, so this appears only with an engine that ignored it.
 */
export function heldBackSentence(n: number): string | null {
  if (!Number.isFinite(n) || n <= 0) return null;
  return n === 1
    ? "Draft mode held back 1 whole-document suggestion."
    : `Draft mode held back ${n.toLocaleString("en-GB")} whole-document suggestions.`;
}

export function applyFilter(list: readonly Suggestion[], filter: Filter): Suggestion[] {
  return filter === "all" ? [...list] : list.filter((s) => s.category === filter);
}

/** How many shown suggestions sit in each detected section (for the section chooser). */
export function countBySection(list: readonly Suggestion[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of list) out[s.section] = (out[s.section] ?? 0) + 1;
  return out;
}

/**
 * The section view: sentence-level suggestions from that section, and the
 * document-wide ones (figure references, abbreviations defined once) kept
 * aside so they are never lost. With "all", everything is in `inSection`.
 */
export function applySectionFilter(list: readonly Suggestion[], section: SectionFilter, known: ScopeMap | null): SectionSplit<Suggestion> {
  if (section === "all") return { inSection: [...list], wholeDocument: [], elsewhere: 0 };
  return splitForSection(list, (s) => s.section === section, known);
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The sentence announced to screen readers when a check completes. */
export function summarySentence(list: readonly Suggestion[]): string {
  if (list.length === 0) return "Check complete. No suggestions.";
  const counts = countByCategory(list);
  const parts = CATEGORY_ORDER.filter((c) => counts[c] > 0).map((c) =>
    plural(counts[c], CATEGORIES[c].label.toLowerCase(), CATEGORIES[c].plural.toLowerCase()),
  );
  return `Check complete. ${plural(list.length, "suggestion", "suggestions")}: ${parts.join(", ")}.`;
}
