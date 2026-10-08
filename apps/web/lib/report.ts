/**
 * The printable report's context block (Codex review R8): what a reader of
 * the PDF needs to interpret it without the app: when the text was checked
 * and when printed, the mode and article type, any tier that was not
 * available, what was skipped while reading, what Draft held back, what
 * the writer dismissed, and whether the editor has changed since. Pure and
 * unit-tested; nothing here leaves the browser.
 */
import type { Mode, TierHealth } from "@researchly/contract";
import { printedAt } from "./print";

/** The report's two times: the check (when its answer arrived) and the printing. */
export function timesLine(checkedAt: Date | null | undefined, at: Date, locale?: string): string {
  const printed = `Printed ${printedAt(at, locale)}`;
  return checkedAt ? `Checked ${printedAt(checkedAt, locale)} · ${printed}` : printed;
}

export function modeLabel(mode: Mode | null | undefined): string {
  return mode === "draft" ? "Draft mode" : "Revise mode";
}

/**
 * Every tier that was not contributing to this check, by its label, in the
 * engine's order. The screen's banner leaves out an expected absence (the
 * learned tier in a build without a model); on paper every gap is named,
 * so a PDF never implies a check that did not run.
 */
export function unavailableTiers(health: readonly TierHealth[] | null | undefined): string[] {
  const out: string[] = [];
  for (const t of health ?? []) {
    const label = (t.label || t.tier).trim();
    if (!t.ok && label && !out.includes(label)) out.push(label);
  }
  return out;
}

export function unavailableLine(labels: readonly string[]): string | null {
  return labels.length > 0 ? `Not available for this check: ${labels.join(", ")}.` : null;
}

/** What was skipped or approximated while reading, from the response and the file's own reading, once each. */
export function readWarnings(responseWarnings: readonly string[] | null | undefined, sourceWarnings?: readonly string[] | null): string[] {
  const out: string[] = [];
  for (const w of [...(sourceWarnings ?? []), ...(responseWarnings ?? [])]) {
    const t = w.trim();
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

/** The label a report carries when the editor changed after the check. */
export const STALE_REPORT_LINE = "This report describes the version that was checked, not the text now in the editor.";

/** Suggestions the writer dismissed on screen are left off the paper, and the paper says so. */
export function dismissedReportLine(n: number): string | null {
  if (n <= 0) return null;
  return n === 1
    ? "1 suggestion dismissed on screen is left out of this report."
    : `${n.toLocaleString("en-GB")} suggestions dismissed on screen are left out of this report.`;
}
