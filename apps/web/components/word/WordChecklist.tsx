"use client";

import type { ChecklistItem } from "@researchly/contract";
import { itemStatusWord, type ChecklistState } from "@/lib/word/checklist";

interface Props {
  state: ChecklistState;
  /** Switches to Revise and checks again (the pane's stage control). */
  onSwitchToRevise?: () => void;
}

/**
 * The reporting checklist in the Word pane (S4c): a minimal list, one row
 * per item with its topic, the question, a status word, and either the
 * writer's own sentence quoted (reported) or the plain reason it matters
 * (needs your check). Reporting only, never the science; "needs your check"
 * is a prompt, since the item may sit in a table, a figure or the
 * supplement. No meter, no colour by status, no tally beyond the engine's
 * own note.
 */
export function WordChecklist({ state, onSwitchToRevise }: Props) {
  if (state.kind === "needs_revise") {
    return (
      <p className="brief-line" data-testid="checklist-needs-revise">
        <span>The reporting checklist reads the whole document, so it needs Revise mode.</span>
        {onSwitchToRevise ? (
          <button type="button" className="btn-link" onClick={onSwitchToRevise} data-testid="checklist-switch-revise">
            Switch to Revise
          </button>
        ) : null}
      </p>
    );
  }
  if (state.kind === "none_suggested") {
    return (
      <p className="brief-line" data-testid="checklist-none">
        Nothing in the text points to a reporting checklist. Choose one under Reporting checklist to check against it.
      </p>
    );
  }
  if (state.kind === "missing") {
    return (
      <p className="brief-line" data-testid="checklist-missing">
        This engine did not return a reporting checklist for this check.
      </p>
    );
  }
  const r = state.report;
  return (
    <div className="wchecklist" data-testid="word-checklist">
      <h3 className="wchecklist-title">
        {r.label} <span className="wchecklist-design">for {r.design}</span>
      </h3>
      <p className="help wchecklist-note" data-testid="checklist-note">
        {r.note}
      </p>
      <ol className="wchecklist-items">
        {r.items.map((item) => (
          <Item key={item.id} item={item} />
        ))}
      </ol>
      <p className="card-source">
        <span className="card-source-label">Source:</span> <cite>{r.source}</cite>
      </p>
    </div>
  );
}

function Item({ item }: { item: ChecklistItem }) {
  const evidence = item.status === "reported" ? (item.evidence ?? "").trim() : "";
  return (
    <li className="wchecklist-item" data-testid="checklist-item" data-status={item.status}>
      <p className="wchecklist-topic">
        <span className="wchecklist-topic-name">{item.topic}</span>
        <span className={`wchecklist-status wchecklist-status-${item.status === "reported" ? "reported" : "check"}`}>
          {itemStatusWord(item)}
        </span>
      </p>
      <p className="wchecklist-question">{item.question}</p>
      {evidence ? (
        <p className="wchecklist-evidence">
          <span className="sr-only">Where your text reports it: </span>
          <q>{evidence}</q>
        </p>
      ) : item.plain.trim() ? (
        <p className="wchecklist-plain">{item.plain}</p>
      ) : null}
    </li>
  );
}
