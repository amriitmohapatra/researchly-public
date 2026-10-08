/**
 * Article-type profiles (S4), the critical reader's brief and the narrative
 * map (S4b), as the surfaces present them. Pure and unit-tested; the engine
 * decides what a profile switches off, and this file only words it.
 */
import {
  DOCUMENT_TYPES,
  type DocumentType,
  type Mode,
  type NarrativeMap,
  type ProfileChoice,
  type ProfileInfo,
  type ReviewQuestion,
  type ReviewReport,
} from "@researchly/contract";

export function isDocumentType(v: unknown): v is DocumentType {
  return typeof v === "string" && (DOCUMENT_TYPES as readonly string[]).includes(v);
}

/**
 * The selector's choices when the engine's registry has not arrived or has
 * none (the local server): the contract's list, with the id as its label.
 */
export const FALLBACK_PROFILES: readonly ProfileChoice[] = DOCUMENT_TYPES.map((id) => ({ id, label: id, summary: "" }));

/** The chosen profile's one-line summary, for the help line under the selector. */
export function profileSummary(choices: readonly ProfileChoice[], id: DocumentType): string {
  return choices.find((c) => c.id === id)?.summary ?? "";
}

/**
 * The one quiet line under the results heading saying what the check was
 * run as. The engine's note already reads "Checked as a commentary: …", so
 * when there is one it stands alone. A guessed "general" says nothing: that
 * is the engine's long-standing behaviour, not a finding.
 */
export function profileLine(profile: ProfileInfo | null | undefined): string | null {
  if (!profile) return null;
  // The headings a guess rested on (Codex review R2), so a wrong guess is easy to see and override.
  const evidence = profile.guessed ? (profile.evidence ?? "").replace(/\s+/g, " ").trim() : "";
  if (profile.note.trim()) {
    return evidence ? `${profile.note.trim()} The guess came from the headings: ${evidence}.` : profile.note.trim();
  }
  if (profile.guessed) {
    if (profile.id === "general") return null;
    return evidence ? `Checked as ${profile.label} (from the headings: ${evidence}).` : `Checked as ${profile.label} (from the headings).`;
  }
  return `Checked as ${profile.label}.`;
}

/**
 * The small word after a brief question saying what its answer rests on
 * (Codex review R4). Nothing for "yours" (question A is the writer's), and
 * nothing for a status this page does not know (an older engine).
 */
export const BRIEF_STATUS_WORD: Record<ReviewQuestion["status"], string> = {
  yours: "",
  detected: "detected",
  not_detected: "not detected",
  not_assessed: "not assessed",
  not_applicable: "not applicable",
};

export function briefStatusWord(status: unknown): string {
  return typeof status === "string" && Object.prototype.hasOwnProperty.call(BRIEF_STATUS_WORD, status)
    ? BRIEF_STATUS_WORD[status as ReviewQuestion["status"]]
    : "";
}

/** What the brief tab shows for a check: the brief, or why there is none. */
export type BriefState = { kind: "ready"; review: ReviewReport } | { kind: "needs_revise" } | { kind: "missing" };

export function briefState(data: { mode: Mode; review?: ReviewReport | null }): BriefState {
  if (data.mode === "draft") return { kind: "needs_revise" };
  return data.review ? { kind: "ready", review: data.review } : { kind: "missing" };
}

/** What the narrative-map tab shows for a check (S4b): the map, or why there is none. The brief's pattern. */
export type NarrativeState = { kind: "ready"; narrative: NarrativeMap } | { kind: "needs_revise" } | { kind: "missing" };

export function narrativeState(data: { mode: Mode; narrative?: NarrativeMap | null }): NarrativeState {
  if (data.mode === "draft") return { kind: "needs_revise" };
  return data.narrative ? { kind: "ready", narrative: data.narrative } : { kind: "missing" };
}

/** "once", "3 times": a rule's tally in "Most frequent checks". Plain words, not a score. */
export function timesPhrase(n: number): string {
  return n === 1 ? "once" : `${n.toLocaleString("en-GB")} times`;
}
