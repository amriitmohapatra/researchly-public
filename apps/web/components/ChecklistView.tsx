"use client";

import { useId } from "react";
import type { ChecklistItem, ChecklistReport } from "@researchly/contract";
import { CHECKLIST_SCOPE_LINE, CHECKLIST_STATUS_WORD } from "@/lib/checklists";
import { sectionLabel } from "@/lib/categories";

interface Props {
  report: ChecklistReport;
  /** Items the writer marked "Not applicable" in this session (never stored). */
  notApplicable: ReadonlySet<string>;
  /** Screen only: toggles an item's "Not applicable". Absent on paper. */
  onToggle?: (id: string) => void;
  /** "screen" (default) or "print": on paper there are no toggles. */
  variant?: "screen" | "print";
}

/**
 * The reporting checklist (S4): the fourth view of a check, shown only when
 * a checklist ran. Read top to bottom as a document: the engine's note,
 * then every item in the guideline's order with its topic, its question
 * and its status in words: "reported" with the sentence that reports it
 * (quoted in the serif), or "needs your check" with the reason in everyday
 * words. A "needs your check" is a prompt, never a verdict: the item may
 * be in a table, a figure or the supplement, or not apply, and the writer
 * can say so for this session with "Not applicable". Then the source and
 * the line that bounds it: reporting only, never the science. No colour
 * by status, no meters, no score.
 */
export function ChecklistView({ report: r, notApplicable, onToggle, variant = "screen" }: Props) {
  const idBase = useId();
  const print = variant === "print";
  return (
    <div className={`checklist${print ? " checklist-print" : ""}`} data-testid="checklist" data-checklist={r.id}>
      <p className="checklist-title">
        <span className="checklist-label">{r.label}</span>
        {r.design ? <span className="checklist-design muted"> for {r.design}</span> : null}
      </p>
      {r.note.trim() ? (
        <p className="help checklist-note" data-testid="checklist-note">
          {r.note}
        </p>
      ) : null}
      <ol className="checklist-items">
        {r.items.map((it) => (
          <li key={it.id} className="checklist-item" data-testid="checklist-item" data-item={it.id} data-status={it.status}>
            <Item item={it} na={notApplicable.has(it.id)} onToggle={print ? undefined : onToggle} titleId={`${idBase}-${it.id}`} />
          </li>
        ))}
      </ol>
      <p className="card-source checklist-source">
        <span className="card-source-label">Source:</span> <cite>{r.source}</cite>
      </p>
      <p className="checklist-scope" data-testid="checklist-scope">
        {CHECKLIST_SCOPE_LINE}
      </p>
    </div>
  );
}

function Item({ item: it, na, onToggle, titleId }: { item: ChecklistItem; na: boolean; onToggle?: (id: string) => void; titleId: string }) {
  const where = (it.sections ?? []).map((s) => sectionLabel(s)).filter((s): s is string => s !== null);
  const evidence = (it.evidence ?? "").trim();
  return (
    <>
      <h3 className="checklist-topic" id={titleId}>
        {it.topic}
      </h3>
      <p className="checklist-question">{it.question}</p>
      <p className="checklist-status" data-testid="checklist-status">
        <span className="checklist-status-word">{na ? "not applicable (your call)" : CHECKLIST_STATUS_WORD[it.status]}</span>
        {where.length > 0 && it.status === "needs_check" && !na ? (
          <span className="checklist-where muted"> · readers look in {where.join(", ")}</span>
        ) : null}
      </p>
      {na ? null : it.status === "reported" && evidence ? (
        <blockquote className="checklist-evidence">
          <q>{evidence}</q>
        </blockquote>
      ) : it.plain.trim() ? (
        <p className="checklist-plain">{it.plain}</p>
      ) : null}
      {onToggle ? (
        <button
          type="button"
          className="btn-link btn-link-quiet checklist-na"
          aria-pressed={na}
          aria-describedby={titleId}
          onClick={() => onToggle(it.id)}
          data-testid="checklist-na"
        >
          Not applicable
        </button>
      ) : null}
    </>
  );
}
