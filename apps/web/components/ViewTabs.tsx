"use client";

import type { KeyboardEvent } from "react";

/**
 * The views of one check: the suggestions, the critical reader's brief (S4),
 * the narrative map (S4b) and, when one ran, the reporting checklist (S4).
 */
export type ResultsView = "suggestions" | "brief" | "narrative" | "checklist";

export const VIEWS: readonly { id: ResultsView; label: string }[] = [
  { id: "suggestions", label: "Suggestions" },
  { id: "brief", label: "Reviewer’s brief" },
  { id: "narrative", label: "Narrative map" },
  { id: "checklist", label: "Checklist" },
];

/** The views every check has; the checklist tab is added only when a checklist ran. */
export const BASE_VIEWS: readonly ResultsView[] = ["suggestions", "brief", "narrative"];

/** The ids a tab and its panel point at, from one base (useId). */
export function viewIds(base: string, view: ResultsView) {
  return { tab: `${base}-tab-${view}`, panel: `${base}-panel-${view}` };
}

interface Props {
  view: ResultsView;
  onChange: (v: ResultsView) => void;
  /** Prefix for the tab and panel ids (from useId, so two strips on a page never collide). */
  idBase: string;
  /** Which views to offer, in this order of VIEWS. Default: the three every check has. */
  views?: readonly ResultsView[];
}

/**
 * A quiet tab strip above the results. ARIA tabs: one tab stop, arrow keys
 * move between the tabs and select as they go, Home and End jump.
 */
export function ViewTabs({ view, onChange, idBase, views = BASE_VIEWS }: Props) {
  const tabs = VIEWS.filter((v) => views.includes(v.id));
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = Math.max(
      0,
      tabs.findIndex((v) => v.id === view),
    );
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const target = tabs[next]!.id;
    onChange(target);
    document.getElementById(viewIds(idBase, target).tab)?.focus();
  };

  return (
    <div className="view-tabs" role="tablist" aria-label="Results view">
      {tabs.map((v) => {
        const ids = viewIds(idBase, v.id);
        const on = v.id === view;
        return (
          <button
            key={v.id}
            type="button"
            role="tab"
            id={ids.tab}
            className="view-tab"
            aria-selected={on}
            aria-controls={ids.panel}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(v.id)}
            onKeyDown={onKeyDown}
            data-testid={`view-${v.id}`}
          >
            {v.label}
          </button>
        );
      })}
    </div>
  );
}
