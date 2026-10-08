"use client";

import { useId, type DragEvent, type ReactNode } from "react";
import type { SourceInfo } from "@researchly/contract";
import { formatLabel, isMultiFile } from "@/lib/source";

interface Props {
  name: string;
  source: SourceInfo | null;
  /** AnalyzeFileResponse.warnings (normally the same as source.warnings). */
  extraWarnings?: readonly string[];
  words: number | null;
  loading: boolean;
  problem: string | null;
  showPreferences: boolean;
  onShowPreferences: (v: boolean) => void;
  /** The "Check as" control (S4), the same one the composer shows. */
  typeControl?: ReactNode;
  /** The "Reporting checklist" control (S4), beside "Check as". */
  checklistControl?: ReactNode;
  onChooseFile: () => void;
  onCancel: () => void;
  onBack: () => void;
  dropHandlers: DropHandlers;
  dropOverlay: ReactNode;
}

export interface DropHandlers {
  onDragEnter: (e: DragEvent<HTMLElement>) => void;
  onDragOver: (e: DragEvent<HTMLElement>) => void;
  onDragLeave: (e: DragEvent<HTMLElement>) => void;
  onDrop: (e: DragEvent<HTMLElement>) => void;
}

const nf = new Intl.NumberFormat("en-GB");

/**
 * Stands in for the composer while a file is being checked or read: the
 * file's name, how it was read, what was skipped, and the ways on (a new
 * version, or back to pasting). The text itself is read-only: changes are
 * made in Word or Overleaf.
 */
export function FilePanel({
  name,
  source,
  extraWarnings = [],
  words,
  loading,
  problem,
  showPreferences,
  onShowPreferences,
  typeControl,
  checklistControl,
  onChooseFile,
  onCancel,
  onBack,
  dropHandlers,
  dropOverlay,
}: Props) {
  const ids = { title: useId(), prefs: useId(), note: useId() };
  const files = source ? new Set(source.segments.map((s) => s.path)).size : 0;
  const warnings = source ? [...new Set([...(source.warnings ?? []), ...extraWarnings])] : [];
  const meta = source
    ? [
        isMultiFile(source.segments) ? `${formatLabel(source.format)} project, ${files} files` : formatLabel(source.format),
        words !== null ? `${nf.format(words)} words` : null,
      ]
        .filter(Boolean)
        .join(", ")
    : loading
      ? "Reading and checking… A whole thesis can take about two minutes."
      : null;

  return (
    <section className="panel file-panel drop-zone" aria-labelledby={ids.title} data-testid="file-panel" {...dropHandlers}>
      {dropOverlay}
      <p className="file-kicker">{source ? "Checked file" : "Checking a file"}</p>
      <h2 id={ids.title} className="file-title">
        <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="file-icon">
          <path d="M4 1.5h5L12.5 5v9.5h-8.5z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          <path d="M9 1.5V5h3.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
        <span className="file-name" translate="no" data-testid="file-name">
          {name}
        </span>
      </h2>
      {meta ? <p className="file-meta muted">{meta}</p> : null}
      <p className="file-readonly" id={ids.note}>
        The text below is what Researchly read from your file, and it is read-only here. Make your changes in Word or
        Overleaf, then check the new version.
      </p>

      {warnings.length > 0 ? (
        <div className="notice notice-quiet file-warnings" data-testid="file-warnings">
          <p className="notice-title">Skipped or approximated while reading the file</p>
          <ul className="file-warning-list">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {problem ? (
        <p className="field-problem file-problem" role="alert" data-testid="file-problem">
          {problem}
        </p>
      ) : null}

      <div className="controls">
        {typeControl}
        {checklistControl}
        <label className="control control-toggle" htmlFor={ids.prefs}>
          <input
            id={ids.prefs}
            type="checkbox"
            role="switch"
            className="switch"
            checked={showPreferences}
            onChange={(e) => onShowPreferences(e.target.checked)}
          />
          <span>Show preferences</span>
        </label>
        <div className="control control-actions">
          {loading ? (
            <>
              <span className="busy-label" aria-hidden="true">
                <span className="spinner" />
                Checking…
              </span>
              <button type="button" className="btn btn-quiet" onClick={onCancel}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-secondary" onClick={onChooseFile} data-testid="choose-new-file">
              Check a new version…
            </button>
          )}
          <button type="button" className="btn btn-quiet" onClick={onBack} data-testid="back-to-editor">
            Back to the text editor
          </button>
        </div>
      </div>
    </section>
  );
}
