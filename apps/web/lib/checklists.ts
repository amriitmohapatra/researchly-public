/**
 * Reporting checklists (S4, the discipline packs) as the website presents
 * them: the choices for the selector, the offer when the text's own words
 * point to one, and the words an item's status is said in. The engine
 * decides what a checklist finds; this file only words it. Pure and
 * unit-tested.
 */
import type { ChecklistChoice, ChecklistChoiceInfo, ChecklistItem } from "@researchly/contract";

/** What the selector holds: no checklist, Auto (the one the words point to), or a guideline's id. */
export type ChecklistSetting = ChecklistChoice | "none";

const IDS = ["auto", "strobe", "consort", "prisma", "epiforge"] as const satisfies readonly ChecklistChoice[];

export function isChecklistChoice(v: unknown): v is ChecklistChoice {
  return typeof v === "string" && (IDS as readonly string[]).includes(v);
}

export function isChecklistSetting(v: unknown): v is ChecklistSetting {
  return v === "none" || isChecklistChoice(v);
}

/** The setting as a request option: nothing for "none". */
export function checklistOption(setting: ChecklistSetting): ChecklistChoice | null {
  return setting === "none" ? null : setting;
}

/**
 * The choices when the engine's registry has not arrived or has none (the
 * local server, an older engine): the engine's own list (packs/
 * epidemiology.py), so the labels read the same either way.
 */
export const FALLBACK_CHECKLISTS: readonly ChecklistChoiceInfo[] = [
  { id: "strobe", label: "STROBE", design: "observational studies (cohort, case-control, cross-sectional)", pack: "Epidemiology" },
  { id: "consort", label: "CONSORT", design: "randomised controlled trials", pack: "Epidemiology" },
  { id: "prisma", label: "PRISMA", design: "systematic reviews and meta-analyses", pack: "Epidemiology" },
  { id: "epiforge", label: "EPIFORGE", design: "epidemic forecasts, projections and predictions", pack: "Epidemiology" },
];

/** The help line under the selector: what the chosen checklist is for. */
export function checklistHelp(choices: readonly ChecklistChoiceInfo[], setting: ChecklistSetting): string {
  if (setting === "none") return "";
  if (setting === "auto") return "The checklist your text's own words point to, if any.";
  const c = choices.find((x) => x.id === setting);
  return c?.design ? `For ${c.design}.` : "";
}

/** One study of each design, in the singular, for the offer's sentence. */
const ONE_OF: Record<string, string> = {
  strobe: "an observational study",
  consort: "a randomised controlled trial",
  prisma: "a systematic review or meta-analysis",
  epiforge: "an epidemic forecast",
};

export interface ChecklistOffer {
  id: ChecklistChoice;
  label: string;
  sentence: string;
}

/**
 * The quiet offer under the results when no checklist was chosen and the
 * engine says the text's words point to one: "This reads like an epidemic
 * forecast. Check it against EPIFORGE?" The label comes from the registry
 * (or the fallback list); a design this page has no singular for is named
 * from the registry's own words. Null when there is nothing to offer or
 * the id is not one this page can ask for.
 */
export function checklistOffer(suggested: string | null | undefined, choices: readonly ChecklistChoiceInfo[]): ChecklistOffer | null {
  if (!suggested || suggested === "auto" || !isChecklistChoice(suggested)) return null;
  const c = choices.find((x) => x.id === suggested) ?? FALLBACK_CHECKLISTS.find((x) => x.id === suggested);
  if (!c) return null;
  const like = ONE_OF[c.id] ?? `a study ${c.label} covers (${c.design})`;
  return { id: suggested, label: c.label, sentence: `This reads like ${like}. Check it against ${c.label}?` };
}

/** The word an item's status is said in: never a colour, never a verdict on the science. */
export const CHECKLIST_STATUS_WORD: Record<ChecklistItem["status"], string> = {
  reported: "reported",
  needs_check: "needs your check",
};

/** The closing line of every checklist view, on screen and on paper. */
export const CHECKLIST_SCOPE_LINE = "This checks reporting only, never the science.";
