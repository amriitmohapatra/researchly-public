/**
 * The Label page's model (S4 exit check): verdicts on flags, exported in
 * exactly the format ml/eval/label_precision.py reads. Pure and unit-tested.
 *
 * A label holds the paragraph number, the rule id, the category, the
 * section and the verdict. Never the paragraph, never the flagged words:
 * the Python reader refuses a label with any other field.
 */
import type { Category } from "@researchly/contract";

export type Verdict = "useful" | "wrong" | "unsure";
export const VERDICTS: readonly Verdict[] = ["useful", "wrong", "unsure"];

/** The sections a labelled paragraph can be checked as (the guide asks for a spread across them). */
export const LABEL_SECTIONS = [
  { id: "introduction", label: "Introduction" },
  { id: "methods", label: "Methods" },
  { id: "results", label: "Results" },
  { id: "discussion", label: "Discussion" },
  { id: "abstract", label: "Abstract" },
  { id: "conclusion", label: "Conclusion" },
] as const;
export type LabelSection = (typeof LABEL_SECTIONS)[number]["id"];

/** The guide's target: fifty paragraphs. */
export const TARGET_PARAGRAPHS = 50;

export interface Label {
  paragraph: number;
  rule_id: string;
  category: Category | string;
  section: string;
  verdict: Verdict;
}

/** What the page keeps between reloads: the paragraph being labelled and the labels so far. */
export interface LabelSession {
  paragraph: number;
  labels: Label[];
}

export const EMPTY_SESSION: LabelSession = { paragraph: 1, labels: [] };

export function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && (VERDICTS as readonly string[]).includes(v);
}

export function isLabelSection(v: unknown): v is LabelSection {
  return typeof v === "string" && LABEL_SECTIONS.some((s) => s.id === v);
}

const SHORT = /^[A-Za-z0-9_.-]{1,40}$/;

/** One stored label, re-built field by field so nothing else (and never text) survives a round trip. */
function toLabel(x: unknown): Label | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  if (!isVerdict(o.verdict) || typeof o.rule_id !== "string" || !SHORT.test(o.rule_id)) return null;
  if (typeof o.paragraph !== "number" || !Number.isInteger(o.paragraph) || o.paragraph < 1) return null;
  const category = typeof o.category === "string" && SHORT.test(o.category) ? o.category : "unknown";
  const section = typeof o.section === "string" && SHORT.test(o.section) ? o.section : "unknown";
  return { paragraph: o.paragraph, rule_id: o.rule_id, category, section, verdict: o.verdict };
}

/** A stored session, or the empty one when the store is missing, from an older page or tampered with. */
export function normaliseSession(raw: unknown): LabelSession {
  if (typeof raw !== "object" || raw === null) return EMPTY_SESSION;
  const o = raw as Record<string, unknown>;
  const labels = Array.isArray(o.labels) ? o.labels.map(toLabel).filter((l): l is Label => l !== null) : [];
  const last = labels.reduce((m, l) => Math.max(m, l.paragraph), 0);
  const p = typeof o.paragraph === "number" && Number.isInteger(o.paragraph) && o.paragraph >= 1 ? o.paragraph : 1;
  return { paragraph: Math.max(p, last), labels };
}

/** How many paragraphs have at least one label. */
export function paragraphsLabelled(s: LabelSession): number {
  return new Set(s.labels.map((l) => l.paragraph)).size;
}

/** "12 of 50 paragraphs, 37 flags labelled" */
export function progressLine(s: LabelSession): string {
  const p = paragraphsLabelled(s);
  const n = s.labels.length;
  return `${p} of ${TARGET_PARAGRAPHS} paragraphs, ${n.toLocaleString("en-GB")} ${n === 1 ? "flag" : "flags"} labelled`;
}

/**
 * Give the flag at `slot` in this paragraph a verdict. `slots` maps a card
 * (by its suggestion id) to its label's index, so changing one's mind
 * replaces the label instead of adding a second.
 */
export function setVerdict(
  s: LabelSession,
  slots: Readonly<Record<string, number>>,
  card: { id: string; rule_id: string; category: string },
  section: string,
  verdict: Verdict,
): { session: LabelSession; slots: Record<string, number> } {
  const label: Label = { paragraph: s.paragraph, rule_id: card.rule_id, category: card.category, section, verdict };
  const at = slots[card.id];
  if (at !== undefined && s.labels[at]?.paragraph === s.paragraph) {
    const labels = [...s.labels];
    labels[at] = label;
    return { session: { ...s, labels }, slots: { ...slots } };
  }
  return { session: { ...s, labels: [...s.labels, label] }, slots: { ...slots, [card.id]: s.labels.length } };
}

/** "Next paragraph": the next number, once the current one has a label (an unlabelled paragraph keeps its number). */
export function nextParagraph(s: LabelSession): LabelSession {
  return s.labels.some((l) => l.paragraph === s.paragraph) ? { ...s, paragraph: s.paragraph + 1 } : s;
}

/** The exported file: `{"version": 1, "labels": [...]}`, the five fields of each label, nothing else. */
export function exportLabels(s: LabelSession): { version: 1; labels: Label[] } {
  return {
    version: 1,
    labels: s.labels.map((l) => ({
      paragraph: l.paragraph,
      rule_id: l.rule_id,
      category: l.category,
      section: l.section,
      verdict: l.verdict,
    })),
  };
}

export const EXPORT_FILENAME = "researchly-labels.json";

/** The file's text: pretty enough to read, exactly what the Python reader loads. */
export function exportText(s: LabelSession): string {
  return `${JSON.stringify(exportLabels(s), null, 2)}\n`;
}

/** The text sent to the engine: the section's name as a heading line above the paragraph (the section decides the advice). */
export function labelContent(section: LabelSection, paragraph: string): string {
  const name = LABEL_SECTIONS.find((s) => s.id === section)?.label ?? "Introduction";
  return `${name}\n\n${paragraph.trim()}\n`;
}
