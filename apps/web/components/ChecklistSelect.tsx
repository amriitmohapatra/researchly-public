"use client";

import { useId } from "react";
import type { ChecklistChoiceInfo } from "@researchly/contract";
import { checklistHelp, isChecklistSetting, type ChecklistSetting } from "@/lib/checklists";

interface Props {
  id: string;
  value: ChecklistSetting;
  /** From the engine's registry, or the built-in list while it has not arrived. */
  choices: readonly ChecklistChoiceInfo[];
  onChange: (v: ChecklistSetting) => void;
}

/**
 * "Reporting checklist": beside "Check as" (S4). None by default; Auto
 * checks against the checklist the text's own words point to; or one
 * guideline by name, its design read under the control. Remembered in this
 * browser only (lib/results-prefs.ts).
 */
export function ChecklistSelect({ id, value, choices, onChange }: Props) {
  const helpId = useId();
  const help = checklistHelp(choices, value);
  return (
    <div className="control control-checklist">
      <label htmlFor={id} className="control-label">
        Reporting checklist
      </label>
      <select
        id={id}
        className="select"
        value={value}
        aria-describedby={help ? helpId : undefined}
        onChange={(e) => {
          const v = e.target.value;
          if (isChecklistSetting(v)) onChange(v);
        }}
        data-testid="checklist-select"
      >
        <option value="none">None</option>
        <option value="auto" title="The checklist your text's own words point to, if any.">
          Auto
        </option>
        {/* Only guidelines this page can ask for: a newer engine's extra ids wait for the contract. */}
        {choices
          .filter((c) => isChecklistSetting(c.id) && c.id !== "auto" && c.id !== "none")
          .map((c) => (
          <option key={c.id} value={c.id} title={c.design || undefined}>
            {c.label}
          </option>
          ))}
      </select>
      {help ? (
        <p id={helpId} className="help control-help" data-testid="checklist-help">
          {help}
        </p>
      ) : null}
    </div>
  );
}
