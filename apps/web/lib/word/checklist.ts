/**
 * The reporting checklist in the Word taskpane (S4c): the choices, what the
 * Checklist tab shows for a check, and the words for an item's status. Pure
 * except for the hook, and unit-tested. A checklist checks reporting only,
 * never the science; "needs your check" is a prompt, never a verdict.
 */
import type { ChecklistChoiceInfo, ChecklistItem, ChecklistReport, Mode } from "@researchly/contract";
import type { ChecklistPref } from "../prefs";
import { useRegistry } from "../registry";

/**
 * The checklists when the engine's registry has not arrived or does not list
 * them (the local server, an older build): the epidemiology pack's four, as
 * packages/core/researchly/packs lists them.
 */
export const FALLBACK_CHECKLISTS: readonly ChecklistChoiceInfo[] = [
  { id: "strobe", label: "STROBE", design: "observational studies (cohort, case-control, cross-sectional)", pack: "Epidemiology" },
  { id: "consort", label: "CONSORT", design: "randomised controlled trials", pack: "Epidemiology" },
  { id: "prisma", label: "PRISMA", design: "systematic reviews and meta-analyses", pack: "Epidemiology" },
  { id: "epiforge", label: "EPIFORGE", design: "epidemic forecasts, projections and predictions", pack: "Epidemiology" },
];

function looksLikeChecklist(c: unknown): c is ChecklistChoiceInfo {
  if (typeof c !== "object" || c === null) return false;
  const o = c as Record<string, unknown>;
  return typeof o.id === "string" && typeof o.label === "string" && typeof o.design === "string";
}

/** The registry's checklists, if the response carried them (GET /v1/rules `checklists`, S4); else null. */
export function registryChecklists(registry: unknown): ChecklistChoiceInfo[] | null {
  const list = (registry as { checklists?: unknown } | null)?.checklists;
  if (!Array.isArray(list)) return null;
  const ok = list.filter(looksLikeChecklist);
  return ok.length > 0 ? ok : null;
}

/** The select's options: None, Auto, then each checklist by its label. */
export function checklistOptions(list: readonly ChecklistChoiceInfo[]): { value: ChecklistPref; label: string }[] {
  return [
    { value: "none", label: "None" },
    { value: "auto", label: "Auto" },
    ...list.filter((c) => c.id !== "auto").map((c) => ({ value: c.id as ChecklistPref, label: c.label })),
  ];
}

/** The help line under the select for a choice. */
export function checklistHelp(list: readonly ChecklistChoiceInfo[], value: ChecklistPref): string {
  if (value === "none") return "No reporting checklist. Checked in Revise only, like the brief.";
  if (value === "auto") return "The checklist your text's own words point to, if any. Reporting only, never the science.";
  const c = list.find((x) => x.id === value);
  return c ? `For ${c.design}. Reporting only, never the science.` : "Reporting only, never the science.";
}

/** The checklists with the engine's labels when it has them, else the built-in list. */
export function useChecklistChoices(engineUrl: string | null): readonly ChecklistChoiceInfo[] {
  const registry = useRegistry(engineUrl, true);
  return registryChecklists(registry) ?? FALLBACK_CHECKLISTS;
}

/** What the Checklist tab shows for a check. */
export type ChecklistState =
  | { kind: "ready"; report: ChecklistReport }
  | { kind: "needs_revise" }
  /** Asked for "auto", and nothing in the text points to a checklist. */
  | { kind: "none_suggested" }
  /** Asked for one, and the engine returned nothing (an engine without checklists). */
  | { kind: "missing" };

export function checklistState(
  data: { mode: Mode; checklist?: ChecklistReport | null },
  asked: ChecklistPref | null,
): ChecklistState {
  if (data.checklist) return { kind: "ready", report: data.checklist };
  if (data.mode === "draft") return { kind: "needs_revise" };
  return asked === "auto" ? { kind: "none_suggested" } : { kind: "missing" };
}

/** The status in a word or two: a prompt, never a verdict. */
export function itemStatusWord(item: Pick<ChecklistItem, "status">): string {
  return item.status === "reported" ? "Reported" : "Needs your check";
}

/** The label of a suggested checklist id, for "Your text's words point to STROBE." */
export function checklistLabel(list: readonly ChecklistChoiceInfo[], id: string | null | undefined): string | null {
  if (!id) return null;
  return list.find((c) => c.id === id)?.label ?? id.toUpperCase();
}
