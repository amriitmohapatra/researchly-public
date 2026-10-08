/** Pure view-model helpers for the Word taskpane (unit-tested). */
import type { AnalyzeWordResponse, Coverage, ProfileInfo, WordParagraph, WordSuggestion } from "@researchly/contract";
import { CATEGORY_ORDER } from "../categories";
import { profileLine } from "../profiles";
import { splitForSection, type ScopeMap, type SectionSplit } from "../scope";

/** Preferences hidden unless asked for (CLAUDE.md #3); the rest in document order. */
export function shownWordSuggestions(data: AnalyzeWordResponse, showPreferences: boolean): WordSuggestion[] {
  const list = showPreferences ? data.suggestions : data.suggestions.filter((s) => s.category !== "preference");
  return [...list].sort(
    (a, b) =>
      a.location.paragraph - b.location.paragraph ||
      a.location.start - b.location.start ||
      CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
}

/** "a, b and c" */
export function listSentence(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-GB")} ${n === 1 ? one : many}`;

/** What was read and what was not, said plainly: silence would read as "nothing to flag". */
export function coverageSentences(c: Coverage): { checked: string; notChecked: string | null } {
  const tables = c.table_paragraphs > 0 ? `, ${plural(c.table_paragraphs, "of them in a table", "of them in tables")}` : "";
  const checked = `Checked ${plural(c.paragraphs, "paragraph", "paragraphs")} of the document body${tables}.`;
  const parts = c.not_checked.filter((p) => p.trim());
  if (parts.length === 0) return { checked, notChecked: null };
  const first = listSentence(parts);
  return { checked, notChecked: `${first.charAt(0).toUpperCase()}${first.slice(1)} ${parts.length === 1 ? "was" : "were"} not checked.` };
}

/** Draft mode's note: what it held back, and that it is a stage, not a verdict. */
export function heldBackSentence(n: number): string | null {
  if (n <= 0) return null;
  return `Draft held back ${plural(n, "document-level suggestion", "document-level suggestions")}, such as figure references and abbreviations defined once.`;
}

/** The sentence announced to screen readers when a check completes. */
export function wordSummary(shown: number): string {
  return shown === 0 ? "Check complete. No suggestions." : `Check complete. ${plural(shown, "suggestion", "suggestions")}.`;
}

/* ---------- "Check this section" ---------- */

/** The stretch of paragraphs the cursor is in: from its heading to the next. */
export interface SectionFocus {
  /** First paragraph of the section (the heading itself, when there is one). */
  start: number;
  /** One past the last paragraph. */
  end: number;
  /** The heading's text, or null when the cursor is above the first heading. */
  heading: string | null;
}

/** A body paragraph in a heading style ("Heading 1", "Heading1", "Title"). Table cells never count. */
export function isHeadingParagraph(p: WordParagraph): boolean {
  return p.kind !== "table" && /^(heading\s*\d+|title)$/i.test(p.style.trim());
}

/**
 * The section containing paragraph `index`: from the nearest heading-styled
 * paragraph at or before it to the next heading. The whole document is
 * still checked; this only says which paragraphs to show.
 */
export function sectionAround(paragraphs: readonly WordParagraph[], index: number): SectionFocus {
  const n = paragraphs.length;
  const at = Math.min(Math.max(index, 0), Math.max(n - 1, 0));
  let start = 0;
  let heading: string | null = null;
  for (let i = at; i >= 0; i--) {
    const p = paragraphs[i];
    if (p && isHeadingParagraph(p)) {
      start = i;
      heading = p.text.trim() || null;
      break;
    }
  }
  let end = n;
  for (let i = at + 1; i < n; i++) {
    const p = paragraphs[i];
    if (p && isHeadingParagraph(p)) {
      end = i;
      break;
    }
  }
  return { start, end, heading };
}

/** The suggestions to list for a section: those in its paragraphs, plus the document-wide ones kept aside. */
export function sectionView(list: readonly WordSuggestion[], focus: SectionFocus, known: ScopeMap | null): SectionSplit<WordSuggestion> {
  return splitForSection(list, (s) => s.location.paragraph >= focus.start && s.location.paragraph < focus.end, known);
}

/** How the section is named in the pane. */
export function sectionName(focus: SectionFocus): string {
  return focus.heading ? `“${focus.heading}”` : "the part before the first heading";
}

/** The sentence announced to screen readers after "Check this section". */
export function sectionSummary(split: SectionSplit<WordSuggestion>, focus: SectionFocus): string {
  const listed = split.inSection.length + split.wholeDocument.length;
  const head = listed === 0 ? `Check complete. No suggestions in ${sectionName(focus)}.` : `Check complete. ${plural(listed, "suggestion", "suggestions")} in ${sectionName(focus)}.`;
  return split.elsewhere > 0 ? `${head} ${plural(split.elsewhere, "more", "more")} elsewhere in the document.` : head;
}

/* ---------- what the check ran as (S4c) ---------- */

/**
 * The profile line in the pane: the website's line, which names the headings
 * a guess rested on ("from the headings: Methods, Results"), so the writer
 * can see why and choose otherwise. One helper, so the two never differ.
 */
export function wordProfileLine(profile: ProfileInfo | null | undefined): string | null {
  return profileLine(profile);
}

/* ---------- after an edit in the document (S4c, Codex review R3) ---------- */

/**
 * The suggestions an edit in paragraph `paragraph` has made stale: every
 * other one located in that paragraph (their offsets may have moved). They
 * keep "Show in document", which re-verifies the text before selecting, but
 * lose Apply until the document is checked again.
 */
export function staleAfterEdit(list: readonly WordSuggestion[], paragraph: number, except: string): string[] {
  return list.filter((s) => s.location.paragraph === paragraph && s.id !== except).map((s) => s.id);
}

export const STALE_NOTE =
  "The text here changed after the check, so this suggestion may have moved. Check the document again before acting on it.";
