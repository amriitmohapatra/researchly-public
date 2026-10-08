"use client";

import { memo, useCallback, type KeyboardEvent, type MouseEvent } from "react";
import type { Segment } from "@/lib/segments";
import { categoryMeta } from "@/lib/categories";

interface Props {
  segments: readonly Segment[];
  activeId: string | null;
  onSelect: (ids: readonly string[]) => void;
  /** Accessible name of the region (defaults to the pasted-text wording). */
  label?: string;
}

/**
 * The submitted text, rendered strictly as text nodes (never innerHTML) with
 * highlight elements around flagged stretches. One tab stop: inside it,
 * arrow keys move between highlights and Enter opens the suggestion.
 */
export const DocumentView = memo(function DocumentView({ segments, activeId, onSelect, label }: Props) {
  const onClick = useCallback(
    (e: MouseEvent<HTMLElement>) => {
      const el = (e.target as HTMLElement).closest<HTMLElement>("[data-sids]");
      if (!el) return;
      onSelect((el.dataset.sids ?? "").split(" ").filter(Boolean));
    },
    [onSelect],
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const root = e.currentTarget;
      const marks = Array.from(root.querySelectorAll<HTMLElement>("[data-sids]"));
      if (marks.length === 0) return;
      const current = document.activeElement instanceof HTMLElement ? marks.indexOf(document.activeElement) : -1;
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        marks[current < 0 ? 0 : Math.min(current + 1, marks.length - 1)]?.focus();
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        marks[current < 0 ? 0 : Math.max(current - 1, 0)]?.focus();
      } else if ((e.key === "Enter" || e.key === " ") && current >= 0) {
        e.preventDefault();
        onSelect((marks[current]!.dataset.sids ?? "").split(" ").filter(Boolean));
      }
    },
    [onSelect],
  );

  return (
    // A scrollable region must be keyboard reachable, hence tabIndex 0.
    <div
      className="doc"
      role="region"
      aria-label={label ?? "Your text, with highlighted suggestions"}
      aria-describedby="doc-help"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={onKeyDown}
      data-testid="document"
    >
      {segments.map((s) => {
        if (s.kind === "point") {
          return (
            <span
              key={`p${s.at}`}
              className={`pt pt-${categoryMeta(s.category).id}${s.ids.includes(activeId ?? "") ? " is-active" : ""}`}
              data-sids={s.ids.join(" ")}
              tabIndex={-1}
            >
              <span className="sr-only">(insertion point)</span>
            </span>
          );
        }
        if (s.ids.length === 0) return <span key={`t${s.start}`}>{s.text}</span>;
        const primary = categoryMeta(s.category ?? "improvement").id;
        const active = activeId !== null && s.ids.includes(activeId);
        return (
          <mark
            key={`m${s.start}`}
            className={`hl hl-${primary}${s.ids.length > 1 ? " hl-multi" : ""}${active ? " is-active" : ""}`}
            data-sids={s.ids.join(" ")}
            data-category={primary}
            tabIndex={-1}
          >
            {s.text}
          </mark>
        );
      })}
    </div>
  );
});
