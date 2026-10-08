/**
 * What the results remember in this browser (S4): the reporting checklist
 * to check against, and nothing else. Never text, never a dismissal.
 * Every storage call is wrapped: private windows and blocked storage just
 * mean the choice is not remembered. scripts/check-boundary.mjs allows
 * storage here and in lib/prefs.ts only.
 */
import { isChecklistSetting, type ChecklistSetting } from "./checklists";

const CHECKLIST_KEY = "researchly.checklist";

export function loadChecklistSetting(): ChecklistSetting | null {
  try {
    const v = window.localStorage.getItem(CHECKLIST_KEY);
    return isChecklistSetting(v) ? v : null;
  } catch {
    return null; // private mode, blocked storage, SSR
  }
}

export function saveChecklistSetting(v: ChecklistSetting): void {
  try {
    window.localStorage.setItem(CHECKLIST_KEY, v);
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}

/** For useSyncExternalStore: another tab changing the choice updates this one. */
export function subscribeChecklistSetting(onChange: () => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key === CHECKLIST_KEY) onChange();
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}
