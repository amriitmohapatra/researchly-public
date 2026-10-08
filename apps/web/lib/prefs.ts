/**
 * The only things this app remembers in the browser: the chosen input format,
 * the article type to check as (S4; shared by the website and the Word add-in,
 * which are one origin) and, in the Word add-in, the engine choice and
 * Draft/Revise and (S4c) the reporting checklist; on the Label page, the
 * verdicts given so far (rule ids and verdicts, never text). The document
 * itself is never persisted (no localStorage, sessionStorage or IndexedDB
 * for text) — scripts/check-boundary.mjs enforces that storage APIs are used
 * in this file only.
 */
import type { ChecklistChoice, DocumentType, Format } from "@researchly/contract";
import { isDocumentType } from "./profiles";
import { isFormat } from "./validate";

const FORMAT_KEY = "researchly.format";
const DOCUMENT_TYPE_KEY = "researchly.document-type";

export function loadFormat(): Format | null {
  try {
    const v = window.localStorage.getItem(FORMAT_KEY);
    return isFormat(v) ? v : null;
  } catch {
    return null; // private mode, blocked storage, SSR
  }
}

export function saveFormat(f: Format): void {
  try {
    window.localStorage.setItem(FORMAT_KEY, f);
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}

/** For useSyncExternalStore: another tab changing the preference updates this one. */
export function subscribeFormat(onChange: () => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key === FORMAT_KEY) onChange();
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

/* ---------- the article type (S4): one choice for both surfaces, never text ---------- */

/** The article type chosen on this computer, or null when never chosen (signed in, the account's choice wins). */
export function loadDocumentTypeChoice(): DocumentType | null {
  const v = read(DOCUMENT_TYPE_KEY);
  return isDocumentType(v) ? v : null;
}

export function saveDocumentTypeChoice(v: DocumentType): void {
  write(DOCUMENT_TYPE_KEY, v);
}

/** For useSyncExternalStore: the website and the taskpane share this choice, so one changing it updates the other. */
export function subscribeDocumentType(onChange: () => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key === DOCUMENT_TYPE_KEY) onChange();
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

/* ---------- the Word add-in (S3): per-viewer choices, never text ---------- */

/** Which engine the add-in checks with: the hosted one, or server.py on this computer (ADR-02 local mode). */
export type EngineChoice = "cloud" | "local";
/** Draft / Revise, remembered here when signed out (signed in, the account holds it). */
export type ModeChoice = "draft" | "revise";

const ENGINE_KEY = "researchly.word.engine";
const MODE_KEY = "researchly.word.mode";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // private mode, blocked storage, SSR
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}

export function loadEngineChoice(): EngineChoice | null {
  const v = read(ENGINE_KEY);
  return v === "cloud" || v === "local" ? v : null;
}

export function saveEngineChoice(v: EngineChoice): void {
  write(ENGINE_KEY, v);
}

export function loadModeChoice(): ModeChoice | null {
  const v = read(MODE_KEY);
  return v === "draft" || v === "revise" ? v : null;
}

export function saveModeChoice(v: ModeChoice): void {
  write(MODE_KEY, v);
}

/** For useSyncExternalStore: another taskpane or tab changing a Word preference updates this one. */
export function subscribeWordPrefs(onChange: () => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key === ENGINE_KEY || e.key === MODE_KEY || e.key === CHECKLIST_KEY) onChange();
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

/* ---------- the reporting checklist (S4c, Word): a choice, never text ---------- */

/** "none", or a checklist the engine checks the text against ("auto": the one the text's words point to). */
export type ChecklistPref = "none" | ChecklistChoice;

const CHECKLIST_KEY = "researchly.word.checklist";
const CHECKLIST_PREFS: readonly string[] = ["none", "auto", "strobe", "consort", "prisma", "epiforge"];

export function isChecklistPref(v: unknown): v is ChecklistPref {
  return typeof v === "string" && CHECKLIST_PREFS.includes(v);
}

/** The checklist chosen on this computer, or null when never chosen (None applies). */
export function loadChecklistChoice(): ChecklistPref | null {
  const v = read(CHECKLIST_KEY);
  return isChecklistPref(v) ? v : null;
}

export function saveChecklistChoice(v: ChecklistPref): void {
  write(CHECKLIST_KEY, v);
}

/* ---------- the Label page (S4 exit check): verdicts on flags, never text ---------- */

const LABELS_KEY = "researchly.labels";

/**
 * The labelling session as stored: the paragraph number being labelled and
 * every label so far (rule id, category, section, verdict). Never the
 * paragraph or the flagged words. lib/labels.ts checks the shape, so a
 * tampered store reads as empty rather than breaking the page.
 */
export function loadLabelStore(): unknown {
  const v = read(LABELS_KEY);
  if (v === null) return null;
  try {
    return JSON.parse(v) as unknown;
  } catch {
    return null;
  }
}

export function saveLabelStore(value: unknown): void {
  write(LABELS_KEY, JSON.stringify(value));
}

export function clearLabelStore(): void {
  try {
    window.localStorage.removeItem(LABELS_KEY);
  } catch {
    /* storage unavailable: nothing was kept */
  }
}
