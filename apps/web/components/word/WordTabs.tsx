"use client";

import type { KeyboardEvent } from "react";
import { VIEWS, type ResultsView } from "../ViewTabs";

/** The pane's views: the site's three, plus the reporting checklist when one was asked for (S4c). */
export type WordView = ResultsView | "checklist";

export function wordViewIds(base: string, view: WordView) {
  return { tab: `${base}-tab-${view}`, panel: `${base}-panel-${view}` };
}

interface Props {
  view: WordView;
  onChange: (v: WordView) => void;
  idBase: string;
  /** Whether the Checklist tab is offered (a checklist was asked for, or one came back). */
  checklist: boolean;
}

/**
 * The taskpane's tab strip: the site's tabs (same labels, classes and test
 * ids as ViewTabs) and, when a reporting checklist was asked for, a fourth,
 * "Checklist". ARIA tabs: one tab stop, arrows move and select, Home and End
 * jump. The strip wraps in the narrow pane, never scrolls.
 */
export function WordTabs({ view, onChange, idBase, checklist }: Props) {
  const shared = VIEWS.filter((v) => (v.id as string) !== "checklist");
  const views: { id: WordView; label: string }[] = [...shared, ...(checklist ? [{ id: "checklist" as const, label: "Checklist" }] : [])];
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = Math.max(0, views.findIndex((v) => v.id === view));
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % views.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + views.length) % views.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = views.length - 1;
    else return;
    e.preventDefault();
    const target = views[next]!.id;
    onChange(target);
    document.getElementById(wordViewIds(idBase, target).tab)?.focus();
  };

  return (
    <div className="view-tabs" role="tablist" aria-label="Results view">
      {views.map((v) => {
        const ids = wordViewIds(idBase, v.id);
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
