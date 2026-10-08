"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal, flushSync } from "react-dom";
import type { AnalyzeResponse, ChecklistChoice, SourceInfo, Suggestion } from "@researchly/contract";
import { CATEGORIES, CATEGORY_ORDER, countByCategory, sectionLabel } from "@/lib/categories";
import type { ChecklistOffer } from "@/lib/checklists";
import { briefState, narrativeState, profileLine } from "@/lib/profiles";
import type { ScopeMap } from "@/lib/scope";
import { resolveSpans, segment } from "@/lib/segments";
import { buildLocator, isMultiFile } from "@/lib/source";
import {
  applyFilter,
  applySectionFilter,
  countBySection,
  dismissedCount,
  heldBackSentence,
  hiddenPreferenceCount,
  shownSuggestions,
  withoutSetAside,
  type Filter,
  type SectionFilter,
} from "@/lib/view";
import { CategoryIcon } from "./CategoryIcon";
import { ChecklistView } from "./ChecklistView";
import { DocumentView } from "./DocumentView";
import { HealthBanner } from "./HealthBanner";
import { MetricsPanel } from "./MetricsPanel";
import { NarrativeMap } from "./NarrativeMap";
import { PrintReport } from "./PrintReport";
import { ReviewBrief } from "./ReviewBrief";
import { SuggestionCard, type CardActions } from "./SuggestionCard";
import { BASE_VIEWS, ViewTabs, viewIds, type ResultsView } from "./ViewTabs";

interface Props {
  data: AnalyzeResponse;
  /** Exactly the text that was sent; offsets refer to this, not to the live editor. */
  submittedText: string;
  showPreferences: boolean;
  stale: boolean;
  busy: boolean;
  onRevealPreferences: () => void;
  /** Present when the text came from an uploaded file (read-only view). */
  source?: SourceInfo | null;
  /** Signed-in card actions (mute, add to dictionary). */
  actions?: CardActions | null;
  /** Rule scopes from the engine's registry, when loaded; null means the built-in list applies. */
  scopes?: ScopeMap | null;
  /** Suggestions, the reviewer's brief (S4), the narrative map (S4b) or the checklist. Held by the parent so a re-check keeps the view. */
  view: ResultsView;
  onView: (v: ResultsView) => void;
  /** When this check's answer arrived: printed in the report's header. */
  checkedAt?: Date | null;
  /** Rules muted since this check: their cards leave at once, before the re-check confirms it. */
  mutedRules?: ReadonlySet<string>;
  /** Check again in Revise (an engine that ran Draft, or a brief that needs it). */
  onRunRevise?: (() => void) | null;
  /** The quiet offer of the checklist the text's words point to (none chosen). */
  checklistOffer?: ChecklistOffer | null;
  onUseChecklist?: ((id: ChecklistChoice) => void) | null;
}

type FocusRequest = { id: string; target: "mark" | "card" | "undo"; seq: number };
type DismissNote = { kind: "dismissed"; id: string } | { kind: "restored"; n: number } | null;

const secondsFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const NO_RULES: ReadonlySet<string> = new Set();

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

const lineFmt = new Intl.NumberFormat("en-GB");

export function Results({
  data,
  submittedText,
  showPreferences,
  stale,
  busy,
  onRevealPreferences,
  source,
  actions,
  scopes = null,
  view,
  onView,
  checkedAt = null,
  mutedRules = NO_RULES,
  onRunRevise = null,
  checklistOffer = null,
  onUseChecklist = null,
}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  // The section the writer is working on. Starts at "all" for every check
  // (the component remounts per check) and is never stored anywhere.
  const [section, setSection] = useState<SectionFilter>("all");
  // "Not an issue here" (review proposal 2): this check only, in memory, never stored or sent.
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const [dismissNote, setDismissNote] = useState<DismissNote>(null);
  // "Not applicable" on checklist items (review proposal 6): this check only, never stored.
  const [notApplicable, setNotApplicable] = useState<ReadonlySet<string>>(() => new Set());
  const sectionId = useId();
  const tabsId = useId();
  const profileText = profileLine(data.profile);
  const heldBack = heldBackSentence(data.hidden_by_mode ?? 0);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [focusReq, setFocusReq] = useState<FocusRequest | null>(null);
  const docColRef = useRef<HTMLDivElement>(null);
  const undoRef = useRef<HTMLButtonElement>(null);
  // The printable report (S4) is mounted only while printing: from the
  // button, or from the browser's own print command (Ctrl/Cmd+P), whose
  // beforeprint event has to see it in the DOM synchronously.
  const [printing, setPrinting] = useState<Date | null>(null);
  const printHelpId = useId();
  const onPrint = useCallback(() => setPrinting(new Date()), []);
  useEffect(() => {
    if (!printing) return;
    const id = window.setTimeout(() => window.print(), 0);
    return () => window.clearTimeout(id);
  }, [printing]);
  useEffect(() => {
    const before = () => flushSync(() => setPrinting((p) => p ?? new Date()));
    const after = () => setPrinting(null);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  const allShown = useMemo(() => shownSuggestions(data, showPreferences), [data, showPreferences]);
  const shown = useMemo(() => withoutSetAside(allShown, dismissed, mutedRules), [allShown, dismissed, mutedRules]);
  const nDismissed = dismissedCount(allShown, dismissed, mutedRules);
  const counts = useMemo(() => countByCategory(shown), [shown]);
  const effectiveFilter: Filter = filter !== "all" && !showPreferences && filter === "preference" ? "all" : filter;
  const byCategory = useMemo(() => applyFilter(shown, effectiveFilter), [shown, effectiveFilter]);
  // The whole document was checked; a chosen section only narrows what is listed.
  const detected = useMemo(() => data.sections_detected.filter((name) => sectionLabel(name) !== null), [data.sections_detected]);
  const effectiveSection: SectionFilter = section !== "all" && !detected.includes(section) ? "all" : section;
  const split = useMemo(() => applySectionFilter(byCategory, effectiveSection, scopes), [byCategory, effectiveSection, scopes]);
  const visible = useMemo(() => [...split.inSection, ...split.wholeDocument], [split]);
  const sectionCounts = useMemo(() => countBySection(shown), [shown]);
  const resolved = useMemo(() => resolveSpans(submittedText, visible), [submittedText, visible]);
  const segments = useMemo(() => segment(submittedText, resolved), [submittedText, resolved]);
  const placeable = useMemo(() => new Set(resolved.map((r) => r.id)), [resolved]);
  const hidden = hiddenPreferenceCount(data, showPreferences);
  // A multi-file upload (an Overleaf project): each card says which file and line it is in.
  const locations = useMemo(() => {
    if (!source || !isMultiFile(source.segments)) return null;
    const locate = buildLocator(source.text, source.segments);
    const out = new Map<string, string>();
    for (const s of data.suggestions) {
      const at = locate(s.span.start);
      if (at) out.set(s.id, `${at.path}, line ${lineFmt.format(at.line)}`);
    }
    return out;
  }, [source, data.suggestions]);

  // The checklist tab exists only when a checklist ran.
  const views: readonly ResultsView[] = data.checklist ? [...BASE_VIEWS, "checklist"] : BASE_VIEWS;
  const effectiveView: ResultsView = views.includes(view) ? view : "suggestions";

  useEffect(() => {
    if (!focusReq) return;
    if (focusReq.target === "undo") {
      undoRef.current?.focus();
      return;
    }
    const el =
      focusReq.target === "mark"
        ? docColRef.current?.querySelector<HTMLElement>(`[data-sids~="${CSS.escape(focusReq.id)}"]`)
        : document.getElementById(`card-${focusReq.id}`);
    if (!el) return;
    el.scrollIntoView({ block: "center", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }, [focusReq]);

  const onSelectFromText = useCallback(
    (ids: readonly string[]) => {
      if (ids.length === 0) return;
      // Overlapping highlights: repeated clicks cycle through every suggestion on that stretch.
      const i = activeId ? ids.indexOf(activeId) : -1;
      const next = i >= 0 && ids.length > 1 ? ids[(i + 1) % ids.length]! : ids[0]!;
      setActiveId(next);
      setFocusReq((r) => ({ id: next, target: "card", seq: (r?.seq ?? 0) + 1 }));
    },
    [activeId],
  );

  const onShowInText = useCallback((id: string) => {
    setActiveId(id);
    setFocusReq((r) => ({ id, target: "mark", seq: (r?.seq ?? 0) + 1 }));
  }, []);

  const onDismiss = useCallback((s: Suggestion) => {
    setDismissed((prev) => new Set(prev).add(s.id));
    setDismissNote({ kind: "dismissed", id: s.id });
    setActiveId((a) => (a === s.id ? null : a));
    // The card is gone: keyboard focus goes to Undo, so the action is one key away.
    setFocusReq((r) => ({ id: s.id, target: "undo", seq: (r?.seq ?? 0) + 1 }));
  }, []);

  // The notice steps aside after a while, but never from under the keyboard: not while focus is on Undo.
  const liveRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!dismissNote) return;
    const id = window.setTimeout(
      () => {
        if (liveRef.current?.contains(document.activeElement)) return;
        setDismissNote(null);
      },
      dismissNote.kind === "dismissed" ? 12_000 : 5_000,
    );
    return () => window.clearTimeout(id);
  }, [dismissNote]);

  const onUndo = () => {
    if (dismissNote?.kind !== "dismissed") return;
    const id = dismissNote.id;
    setDismissed((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    setDismissNote({ kind: "restored", n: 1 });
    setFocusReq((r) => ({ id, target: "card", seq: (r?.seq ?? 0) + 1 }));
  };

  const onShowDismissed = () => {
    const n = nDismissed;
    setDismissed(new Set());
    setDismissNote({ kind: "restored", n });
  };

  const onToggleNotApplicable = useCallback((id: string) => {
    setNotApplicable((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const sections = detected.map(sectionLabel).filter((s): s is string => s !== null);
  const card = (s: Suggestion) => (
    <SuggestionCard
      suggestion={s}
      active={s.id === activeId}
      placeable={placeable.has(s.id)}
      onShowInText={onShowInText}
      location={locations?.get(s.id) ?? null}
      actions={actions}
      onDismiss={onDismiss}
    />
  );
  const seconds = secondsFmt.format(data.elapsed_ms < 10_000 ? data.elapsed_ms / 1000 : Math.round(data.elapsed_ms / 1000));
  const chips: Filter[] = ["all", ...CATEGORY_ORDER.filter((c) => c !== "preference" || showPreferences)];

  // When no suggestion is shown the note still has to be reachable, so it renders in either layout.
  const hiddenNote =
    hidden > 0 ? (
      <p className="hidden-prefs" data-testid="hidden-prefs">
        <CategoryIcon category="preference" />
        <span>
          {hidden} {hidden === 1 ? "preference" : "preferences"} hidden.
        </span>{" "}
        <button type="button" className="btn-link" onClick={onRevealPreferences} aria-label={`Show ${hidden} hidden preferences`}>
          Show
        </button>
      </p>
    ) : null;

  const panelIds = (v: ResultsView) => ({ id: viewIds(tabsId, v).panel, "aria-labelledby": viewIds(tabsId, v).tab });

  return (
    <section className="results" aria-labelledby="results-heading" aria-busy={busy} data-testid="results">
      <div className="results-head">
        <h2 id="results-heading" className="results-title">
          {shown.length === 0 ? "No suggestions" : `${shown.length} ${shown.length === 1 ? "suggestion" : "suggestions"}`}
        </h2>
        <p className="muted results-meta">
          {sections.length > 0 ? <>Sections detected: {sections.join(", ")}</> : <>No section headings detected</>}
          {" · "}checked in {seconds}&nbsp;s
        </p>
        {nDismissed > 0 ? (
          <p className="results-dismissed muted" data-testid="dismissed-line">
            <span>{nDismissed} dismissed</span>
            <span aria-hidden="true"> · </span>
            <button
              type="button"
              className="btn-link"
              onClick={onShowDismissed}
              aria-label={`Show ${nDismissed} dismissed ${nDismissed === 1 ? "suggestion" : "suggestions"}`}
              data-testid="show-dismissed"
            >
              Show
            </button>
          </p>
        ) : null}
        <p className="results-print">
          <button type="button" className="btn-link" onClick={onPrint} aria-describedby={printHelpId} data-testid="print-report-button">
            Print or save as PDF
          </button>
          <span id={printHelpId} className="sr-only">
            Opens your browser&rsquo;s print dialog with the text, its highlights and the suggestions side by side, then the
            reviewer&rsquo;s brief, the narrative map and any reporting checklist. Choose Save as PDF there to keep a file.
            Nothing leaves this page.
          </span>
        </p>
      </div>
      {profileText ? (
        <p className="profile-line muted" data-testid="profile-line">
          {profileText}
        </p>
      ) : null}
      {heldBack ? (
        <p className="results-line" data-testid="held-back">
          <span>{heldBack}</span>
          {onRunRevise ? (
            <button type="button" className="btn-link" onClick={onRunRevise} disabled={busy} data-testid="run-revise">
              Check again in Revise
            </button>
          ) : null}
        </p>
      ) : null}
      {!data.checklist && checklistOffer && onUseChecklist ? (
        <p className="results-line" data-testid="checklist-offer">
          <span>{checklistOffer.sentence}</span>
          <button
            type="button"
            className="btn-link"
            onClick={() => onUseChecklist(checklistOffer.id)}
            disabled={busy}
            data-testid="use-checklist"
          >
            Check against {checklistOffer.label}
          </button>
        </p>
      ) : null}

      <ViewTabs view={effectiveView} onChange={onView} idBase={tabsId} views={views} />

      {stale ? (
        <p className="notice notice-quiet" data-testid="stale-note">
          You have edited the text since this check. The highlights below refer to the version you checked.
        </p>
      ) : null}

      <HealthBanner health={data.health} />

      {!source && (data.warnings?.length ?? 0) > 0 ? (
        <div className="notice notice-quiet read-warnings" data-testid="read-warnings">
          <p className="notice-title">Read with approximations</p>
          <ul className="file-warning-list">
            {data.warnings!.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {effectiveView === "brief" ? (
        <div role="tabpanel" {...panelIds("brief")} className="view-panel" data-testid="brief-panel">
          <ReviewBrief state={briefState(data)} onSwitchToRevise={onRunRevise ?? undefined} />
        </div>
      ) : effectiveView === "narrative" ? (
        <div role="tabpanel" {...panelIds("narrative")} className="view-panel" data-testid="narrative-panel">
          <NarrativeMap state={narrativeState(data)} onSwitchToRevise={onRunRevise ?? undefined} />
        </div>
      ) : effectiveView === "checklist" && data.checklist ? (
        <div role="tabpanel" {...panelIds("checklist")} className="view-panel" data-testid="checklist-panel">
          <ChecklistView report={data.checklist} notApplicable={notApplicable} onToggle={onToggleNotApplicable} />
        </div>
      ) : shown.length === 0 ? (
        <div role="tabpanel" {...panelIds("suggestions")}>
          {hiddenNote}
          <div className="empty" data-testid="empty-state">
            {nDismissed > 0 ? (
              <>
                <p className="empty-title">Every suggestion in this check is dismissed.</p>
                <p className="muted">Use &ldquo;Show&rdquo; beside the heading to bring them back. Nothing was stored.</p>
              </>
            ) : (
              <>
                <p className="empty-title">No suggestions. That&rsquo;s not a score.</p>
                <p className="muted">It means none of our checks fired on this text. The read-outs below still describe it.</p>
              </>
            )}
          </div>
        </div>
      ) : (
        <div role="tabpanel" {...panelIds("suggestions")}>
          <div className="toolbar">
            <div className="filters" role="group" aria-label="Filter suggestions by category">
              {chips.map((c) => {
                const n = c === "all" ? shown.length : counts[c];
                const label = c === "all" ? "All" : CATEGORIES[c].plural;
                return (
                  <button
                    key={c}
                    type="button"
                    className={`chip-btn chip-${c}`}
                    aria-pressed={effectiveFilter === c}
                    onClick={() => setFilter(c)}
                    data-testid={`filter-${c}`}
                  >
                    {c !== "all" ? <CategoryIcon category={c} /> : null}
                    <span className="chip-label">{label}</span>
                    <span className="chip-count">{n}</span>
                  </button>
                );
              })}
            </div>
            {detected.length > 0 ? (
              <div className="control section-control">
                <label htmlFor={sectionId} className="control-label">
                  Section
                </label>
                <select
                  id={sectionId}
                  className="select select-compact"
                  value={effectiveSection}
                  onChange={(e) => setSection(e.target.value)}
                  data-testid="section-filter"
                >
                  <option value="all">All sections ({shown.length})</option>
                  {detected.map((name) => (
                    <option key={name} value={name}>
                      {sectionLabel(name)} ({sectionCounts[name] ?? 0})
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            {hiddenNote}
          </div>
          <p className="filter-blurb muted">
            {effectiveFilter === "all"
              ? "Conventions are research-writing norms you may choose to follow. They are not errors."
              : CATEGORIES[effectiveFilter].blurb}
            {effectiveSection !== "all" ? (
              <>
                {" "}
                <span data-testid="section-blurb">
                  Showing the {sectionLabel(effectiveSection)} section. The whole text was checked; checks that read all of it
                  are listed under &ldquo;Whole document&rdquo;.
                </span>
              </>
            ) : null}
          </p>

          <div className="results-grid">
            <div className="doc-col" ref={docColRef}>
              <h3 className="col-title">{source ? "Your file, as Researchly read it" : "Your text"}</h3>
              <p id="doc-help" className="help">
                {source ? "Read-only. " : ""}Select a highlight to open its suggestion. Keyboard: Tab into the text, move
                with the arrow keys, press Enter.
              </p>
              <DocumentView
                segments={segments}
                activeId={activeId}
                onSelect={onSelectFromText}
                label={source ? "Text read from your file, with highlighted suggestions" : undefined}
              />
            </div>
            <div className="list-col">
              <h3 className="col-title">{effectiveSection === "all" ? "Suggestions" : `Suggestions in ${sectionLabel(effectiveSection)}`}</h3>
              {split.inSection.length === 0 ? (
                <p className="muted" data-testid="no-cards">
                  {effectiveSection === "all"
                    ? `No ${CATEGORIES[effectiveFilter as keyof typeof CATEGORIES]?.plural.toLowerCase() ?? "suggestions"} in this check.`
                    : `No ${effectiveFilter === "all" ? "suggestions" : CATEGORIES[effectiveFilter].plural.toLowerCase()} in the ${sectionLabel(effectiveSection)} section.`}
                </p>
              ) : (
                <ol className="cards" aria-label="Suggestions, in document order">
                  {split.inSection.map((s) => (
                    <li key={s.id}>{card(s)}</li>
                  ))}
                </ol>
              )}
              {split.wholeDocument.length > 0 ? (
                <section className="card-group" aria-labelledby="whole-document-title" data-testid="whole-document">
                  <h4 id="whole-document-title" className="col-title card-group-title">
                    Whole document
                  </h4>
                  <p className="help card-group-help">
                    Checks that read the whole text, such as figure references and abbreviations defined once. They apply
                    wherever you are working.
                  </p>
                  <ol className="cards" aria-label="Whole-document suggestions, in document order">
                    {split.wholeDocument.map((s) => (
                      <li key={s.id}>{card(s)}</li>
                    ))}
                  </ol>
                </section>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* The dismissal notice: a polite live region that is always in the page, so the change is announced. */}
      <div ref={liveRef} className="dismiss-live" role="status" aria-live="polite" data-testid="dismiss-live">
        {dismissNote?.kind === "dismissed" ? (
          <p className="dismiss-note">
            <span>Dismissed.</span>{" "}
            <button type="button" ref={undoRef} className="btn-link" onClick={onUndo} data-testid="undo-dismiss">
              Undo
            </button>
          </p>
        ) : dismissNote?.kind === "restored" ? (
          <p className="dismiss-note">
            {dismissNote.n === 1 ? "Restored." : `${dismissNote.n} suggestions shown again.`}
          </p>
        ) : null}
      </div>

      {data.metrics ? <MetricsPanel metrics={data.metrics} /> : null}

      <p className="engine-meta muted">
        Checked by engine {data.engine.service_version} (core {data.engine.core_version}) with{" "}
        {data.engine.rules_loaded} rules. Each suggestion names its source; open &ldquo;The full reasoning&rdquo; for the detail.
      </p>
      {printing && typeof document !== "undefined"
        ? createPortal(
            <PrintReport
              data={data}
              submittedText={submittedText}
              showPreferences={showPreferences}
              source={source}
              scopes={scopes}
              at={printing}
              checkedAt={checkedAt}
              stale={stale}
              dismissed={dismissed}
              mutedRules={mutedRules}
              locations={locations}
              notApplicable={notApplicable}
            />,
            document.body,
          )
        : null}
    </section>
  );
}
