"use client";

import { useId } from "react";
import type { DocumentType, ProfileChoice } from "@researchly/contract";
import { isDocumentType, profileSummary } from "@/lib/profiles";

interface Props {
  id: string;
  value: DocumentType;
  /** From the engine's registry, or the contract's list while it has not arrived. */
  choices: readonly ProfileChoice[];
  onChange: (v: DocumentType) => void;
  /** A failed save to the account, said under the control. */
  note?: string | null;
}

/**
 * "Check as": the article type the engine judges the text as (S4). Default
 * Auto, which guesses from the headings. The chosen type's one-line summary
 * reads under the control, so the writer knows what the choice changes.
 */
export function ProfileSelect({ id, value, choices, onChange, note }: Props) {
  const helpId = useId();
  const summary = profileSummary(choices, value);
  return (
    <div className="control control-profile">
      <label htmlFor={id} className="control-label">
        Check as
      </label>
      <select
        id={id}
        className="select"
        value={value}
        aria-describedby={summary ? helpId : undefined}
        onChange={(e) => {
          const v = e.target.value;
          if (isDocumentType(v)) onChange(v);
        }}
        data-testid="document-type"
      >
        {choices.map((c) => (
          <option key={c.id} value={c.id} title={c.summary || undefined}>
            {c.label}
          </option>
        ))}
      </select>
      {summary ? (
        <p id={helpId} className="help control-help" data-testid="document-type-help">
          {summary}
        </p>
      ) : null}
      {note ? (
        <p className="field-problem" role="alert" data-testid="document-type-note">
          {note}
        </p>
      ) : null}
    </div>
  );
}
