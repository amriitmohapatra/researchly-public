"use client";

import { useMemo } from "react";
import type { AnalyzeResponse, SourceInfo, Suggestion } from "@researchly/contract";
import { categoryMeta, countByCategory, CATEGORIES, CATEGORY_ORDER, sectionLabel } from "@/lib/categories";
import { markNumbers, numberSuggestions, reportTitle } from "@/lib/print";
import { briefState, narrativeState, profileLine } from "@/lib/profiles";
import {
  dismissedReportLine,
  modeLabel,
  readWarnings,
  STALE_REPORT_LINE,
  timesLine,
  unavailableLine,
  unavailableTiers,
} from "@/lib/report";
import { isDocumentWide, type ScopeMap } from "@/lib/scope";
import { resolveSpans, segment } from "@/lib/segments";
import { dismissedCount, heldBackSentence, shownSuggestions, withoutSetAside } from "@/lib/view";
import { ChecklistView } from "./ChecklistView";
import { NarrativeMap } from "./NarrativeMap";
import { ReviewBrief } from "./ReviewBrief";

const NONE: ReadonlySet<string> = new Set();

interface Props {
  data: AnalyzeResponse;
  submittedText: string;
  showPreferences: boolean;
  source?: SourceInfo | null;
  scopes?: ScopeMap | null;
  /** The moment the report was asked for; fixed by the caller so a re-render does not move it. */
  at: Date;
  /** When the check's answer arrived (Codex review R8): printed beside the print time. */
  checkedAt?: Date | null;
  /** The editor changed after the check: the report says it describes the checked version. */
  stale?: boolean;
  /** Suggestions dismissed on screen ("Not an issue here"): left out, with a count line. */
  dismissed?: ReadonlySet<string>;
  /** Rules muted since the check: left out, as on screen. */
  mutedRules?: ReadonlySet<string>;
  /** For a multi-file upload: suggestion id -> "file, line N", as the cards show it. */
  locations?: ReadonlyMap<string, string> | null;
  /** Checklist items the writer marked "Not applicable" on screen (this session). */
  notApplicable?: ReadonlySet<string>;
}

/**
 * One check on paper (S4): a header that says what the reader needs to
 * interpret it (when checked and printed, the mode and article type, any
 * tier that was not available, what was skipped while reading, what Draft
 * held back, what was dismissed, and whether the editor has changed since;
 * Codex review R8), then the text with its highlights numbered on the left
 * and the suggestions under the same numbers on the right, then the
 * reviewer's brief on its own page, the narrative map (S4b) on the page
 * after it and, when one ran, the reporting checklist. Rendered only for
 * printing (the stylesheet hides it on screen and hides everything else on
 * paper) and mounted only while the print dialog is open, so a long
 * document is not laid out twice for nothing. Everything here is the same
 * data the screen shows; nothing is sent anywhere to make it.
 */
export function PrintReport({
  data,
  submittedText,
  showPreferences,
  source,
  scopes = null,
  at,
  checkedAt = null,
  stale = false,
  dismissed = NONE,
  mutedRules = NONE,
  locations = null,
  notApplicable = NONE,
}: Props) {
  const allShown = useMemo(() => shownSuggestions(data, showPreferences), [data, showPreferences]);
  const shown = useMemo(() => withoutSetAside(allShown, dismissed, mutedRules), [allShown, dismissed, mutedRules]);
  const nDismissed = dismissedCount(allShown, dismissed, mutedRules);
  const inText = useMemo(() => shown.filter((s) => !isDocumentWide(s.rule_id, scopes)), [shown, scopes]);
  const wholeDocument = useMemo(() => shown.filter((s) => isDocumentWide(s.rule_id, scopes)), [shown, scopes]);
  const numbers = useMemo(() => numberSuggestions(inText, wholeDocument), [inText, wholeDocument]);
  const segments = useMemo(() => segment(submittedText, resolveSpans(submittedText, shown)), [submittedText, shown]);
  const counts = countByCategory(shown);
  const countLine = CATEGORY_ORDER.filter((c) => counts[c] > 0)
    .map((c) => `${counts[c]} ${(counts[c] === 1 ? CATEGORIES[c].label : CATEGORIES[c].plural).toLowerCase()}`)
    .join(", ");
  const sections = data.sections_detected.map(sectionLabel).filter((s): s is string => s !== null);
  const profile = profileLine(data.profile);
  const brief = briefState(data);
  const narrative = narrativeState(data);
  const unavailable = unavailableLine(unavailableTiers(data.health));
  const warnings = readWarnings(data.warnings, source?.warnings);
  const heldBack = heldBackSentence(data.hidden_by_mode ?? 0);
  const dismissedLine = dismissedReportLine(nDismissed);

  const item = (s: Suggestion) => {
    const plain = s.plain.trim() || s.why.trim();
    const where = locations?.get(s.id) ?? null;
    return (
      <li key={s.id} className={`print-card print-card-${categoryMeta(s.category).id}`} data-testid="print-card">
        <p className="print-card-head">
          <span className="print-n">{numbers.get(s.id)}</span>
          <span className="print-cat">{categoryMeta(s.category).label}</span>
          {s.section && sectionLabel(s.section) ? <span className="print-sec">{sectionLabel(s.section)}</span> : null}
        </p>
        {where ? (
          <p className="print-loc" data-testid="print-location">
            {where}
          </p>
        ) : null}
        <p className="print-msg">{s.message}</p>
        {s.replacement !== null && s.replacement !== undefined ? (
          <p className="print-repl">Suggested revision (your call): {s.replacement === "" ? <em>remove this</em> : <q>{s.replacement}</q>}</p>
        ) : null}
        {plain ? <p className="print-plain">{plain}</p> : null}
        <p className="print-source">Source: {s.source}</p>
      </li>
    );
  };

  return (
    <div className="print-report" data-testid="print-report">
      <header className="print-head">
        <h1>{reportTitle(source)}</h1>
        <p className="print-meta" data-testid="print-times">
          {timesLine(checkedAt, at)}
        </p>
        <p className="print-meta">
          {shown.length === 0 ? "No suggestions" : `${shown.length} ${shown.length === 1 ? "suggestion" : "suggestions"}`}
          {countLine ? ` (${countLine})` : ""}
          {" · "}
          {sections.length > 0 ? `Sections: ${sections.join(", ")}` : "No section headings detected"}
          {" · "}
          {modeLabel(data.mode)}
        </p>
        {profile ? <p className="print-meta">{profile}</p> : null}
        {stale || unavailable || warnings.length > 0 || heldBack || dismissedLine ? (
          <div className="print-context" data-testid="print-context">
            {stale ? (
              <p className="print-meta print-stale" data-testid="print-stale">
                {STALE_REPORT_LINE}
              </p>
            ) : null}
            {unavailable ? (
              <p className="print-meta" data-testid="print-unavailable">
                {unavailable}
              </p>
            ) : null}
            {heldBack ? (
              <p className="print-meta" data-testid="print-held-back">
                {heldBack} Check again in Revise to include them.
              </p>
            ) : null}
            {dismissedLine ? (
              <p className="print-meta" data-testid="print-dismissed">
                {dismissedLine}
              </p>
            ) : null}
            {warnings.length > 0 ? (
              <div className="print-meta" data-testid="print-warnings">
                <p className="print-meta">Skipped or approximated while reading:</p>
                <ul className="print-warnings">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
        <p className="print-key">
          Each highlight carries the number of its suggestion. Corrections are likely errors; improvements would read more
          easily revised; conventions are norms you may choose to follow; preferences are matters of taste.
        </p>
      </header>

      <section className="print-grid" aria-label="Your text and the suggestions, side by side">
        <div className="print-doc">
          <h2>{source ? "Your file, as Researchly read it" : "Your text"}</h2>
          <div className="print-text">
            {segments.map((s) => {
              if (s.kind === "point") {
                const ns = markNumbers(s, numbers);
                return ns.length > 0 ? (
                  <sup key={`p${s.at}`} className="print-ref">
                    {ns.join(",")}
                  </sup>
                ) : null;
              }
              if (s.ids.length === 0) return <span key={`t${s.start}`}>{s.text}</span>;
              const ns = markNumbers(s, numbers);
              return (
                <mark key={`m${s.start}`} className={`print-hl print-hl-${categoryMeta(s.category ?? "improvement").id}`} data-testid="print-mark">
                  {s.text}
                  {ns.length > 0 ? <sup className="print-ref">{ns.join(",")}</sup> : null}
                </mark>
              );
            })}
          </div>
        </div>
        <div className="print-list">
          <h2>Suggestions</h2>
          {inText.length === 0 && wholeDocument.length === 0 ? <p className="print-muted">None of the checks fired on this text.</p> : null}
          {inText.length > 0 ? <ol className="print-cards">{inText.map(item)}</ol> : null}
          {wholeDocument.length > 0 ? (
            <>
              <h3>Whole document</h3>
              <p className="print-muted">Checks that read the whole text, such as figure references and abbreviations defined once.</p>
              <ol className="print-cards">{wholeDocument.map(item)}</ol>
            </>
          ) : null}
        </div>
      </section>

      <section className="print-brief" aria-label="Reviewer's brief">
        <h2>Reviewer&rsquo;s brief</h2>
        {brief.kind === "ready" ? (
          <ReviewBrief state={brief} />
        ) : brief.kind === "needs_revise" ? (
          <p className="print-muted">This check ran in Draft mode, which has no brief. Check again in Revise mode to include it.</p>
        ) : (
          <p className="print-muted">This engine did not return a brief for this check.</p>
        )}
      </section>

      <section className="print-narrative" aria-label="Narrative map" data-testid="print-narrative">
        <h2>Narrative map</h2>
        {narrative.kind === "ready" ? (
          <NarrativeMap state={narrative} variant="print" />
        ) : narrative.kind === "needs_revise" ? (
          <p className="print-muted">This check ran in Draft mode, which has no narrative map. Check again in Revise mode to include it.</p>
        ) : (
          <p className="print-muted">This engine did not return a narrative map for this check.</p>
        )}
      </section>

      {data.checklist ? (
        <section className="print-checklist" aria-label="Reporting checklist" data-testid="print-checklist">
          <h2>Reporting checklist</h2>
          <ChecklistView report={data.checklist} notApplicable={notApplicable} variant="print" />
        </section>
      ) : null}

      <footer className="print-foot">
        Made in your browser from one check by engine {data.engine.service_version} (core {data.engine.core_version}). Nothing
        was sent anywhere to produce this page, and Researchly stored nothing.
      </footer>
    </div>
  );
}
