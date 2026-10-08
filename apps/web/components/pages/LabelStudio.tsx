"use client";

import { useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { Suggestion } from "@researchly/contract";
import { getEngineAuth } from "@/lib/auth";
import { categoryMeta, CATEGORY_ORDER } from "@/lib/categories";
import { ENGINE_URL } from "@/lib/config";
import { analyze } from "@/lib/engine";
import { clientError, type CheckError } from "@/lib/errors";
import {
  EMPTY_SESSION,
  EXPORT_FILENAME,
  exportText,
  isLabelSection,
  LABEL_SECTIONS,
  labelContent,
  nextParagraph,
  normaliseSession,
  progressLine,
  setVerdict,
  type LabelSection,
  type LabelSession,
  type Verdict,
} from "@/lib/labels";
import { clearLabelStore, loadLabelStore, saveLabelStore } from "@/lib/prefs";
import { CategoryBadge } from "../CategoryIcon";
import { ConfirmDelete } from "./ConfirmDelete";

const GUIDE_URL = "https://github.com/amriitmohapatra/Researchly/blob/main/docs/labelling-guide.md";

const VERDICT_BUTTONS: { id: Verdict; label: string }[] = [
  { id: "useful", label: "Useful" },
  { id: "wrong", label: "Wrong" },
  { id: "unsure", label: "Unsure" },
];

const noSubscribe = () => () => {};

type Phase = "idle" | "checking" | "done" | "error";

/**
 * The Label page (S4 exit check): check one paragraph of your own writing
 * under a section heading, mark each flag Useful, Wrong or Unsure, move to
 * the next paragraph, and export the verdicts for ml/eval/label_precision.py.
 *
 * The paragraph is sent to the engine like any check and never stored. The
 * labels (rule id, category, section, paragraph number, verdict) are kept in
 * this browser so a reload does not lose them; the text is not.
 */
export function LabelStudio() {
  // The stored session is read after hydration only (the server has no storage).
  const hydrated = useSyncExternalStore(noSubscribe, () => true, () => false);
  const stored = useMemo(() => (hydrated ? normaliseSession(loadLabelStore()) : EMPTY_SESSION), [hydrated]);
  const [changed, setChanged] = useState<LabelSession | null>(null);
  const session = changed ?? stored;

  /** Which label each card of this paragraph holds (by suggestion id), so a changed mind replaces it. */
  const [slots, setSlots] = useState<Record<string, number>>({});
  const [section, setSection] = useState<LabelSection>("introduction");
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [cards, setCards] = useState<Suggestion[]>([]);
  const [checkedAs, setCheckedAs] = useState<LabelSection>("introduction");
  const [error, setError] = useState<CheckError | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const ids = { section: useId(), text: useId(), textHelp: useId(), problem: useId() };

  const update = (next: LabelSession) => {
    setChanged(next);
    saveLabelStore(next);
  };

  const verdictFor = (id: string): Verdict | null => {
    const at = slots[id];
    const l = at === undefined ? undefined : session.labels[at];
    return l && l.paragraph === session.paragraph ? l.verdict : null;
  };

  const runCheck = async () => {
    if (phase === "checking") return;
    if (!text.trim()) {
      setProblem("Paste one paragraph of your own writing first.");
      textRef.current?.focus();
      return;
    }
    setProblem(null);
    setError(null);
    setPhase("checking");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r = await analyze(
        { content: labelContent(section, text), format: "plain", showPreferences: false, mode: "revise", signal: ctrl.signal },
        ENGINE_URL,
        getEngineAuth(),
      );
      if (r.ok) {
        const shown = r.data.suggestions
          .filter((s) => s.category !== "preference")
          .sort(
            (a, b) =>
              a.span.start - b.span.start || CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category),
          );
        setCards(shown);
        setCheckedAs(section);
        setPhase("done");
      } else {
        setError(r.error);
        setPhase("error");
      }
    } catch {
      if (ctrl.signal.aborted) setPhase(cards.length ? "done" : "idle");
      else {
        setError(clientError());
        setPhase("error");
      }
    } finally {
      abortRef.current = null;
    }
  };

  const onVerdict = (s: Suggestion, verdict: Verdict) => {
    const r = setVerdict(session, slots, s, checkedAs, verdict);
    setSlots(r.slots);
    update(r.session);
  };

  const onNext = () => {
    abortRef.current?.abort();
    update(nextParagraph(session));
    setSlots({});
    setCards([]);
    setText("");
    setPhase("idle");
    setError(null);
    textRef.current?.focus();
  };

  const onExport = () => {
    if (session.labels.length === 0) return;
    const blob = new Blob([exportText(session)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = EXPORT_FILENAME;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const labelled = cards.filter((c) => verdictFor(c.id) !== null).length;

  return (
    <div className="label-studio" data-testid="label-studio">
      <details className="panel label-help" data-testid="label-help">
        <summary>How to label</summary>
        <div className="label-help-body">
          <p>
            Check one paragraph of your own writing at a time, under the section it comes from. For each flag, answer
            one question: is this flag right, or worth acting on, in this paragraph?
          </p>
          <dl className="label-verdicts">
            <dt>Useful</dt>
            <dd>
              It points at something real: you would change the text, or you are glad to have been asked. A convention
              you choose not to follow still counts, if the convention is real and described correctly.
            </dd>
            <dt>Wrong</dt>
            <dd>A false flag: the flagged words do not have the problem the card describes.</dd>
            <dt>Unsure</dt>
            <dd>You cannot tell without more context, or it is a matter of taste. Counted, but left out of precision.</dd>
          </dl>
          <p>
            Label the flag, not the paragraph, and skip paragraphs with no flags. The aim is 50 paragraphs spread across
            the sections. The full method is in{" "}
            <a className="inline-link" href={GUIDE_URL} rel="noreferrer">
              the labelling guide
            </a>
            .
          </p>
        </div>
      </details>

      <section className="panel label-composer" aria-label="Paragraph to label">
        <p className="label-count" role="status" aria-live="polite" data-testid="label-count">
          Paragraph {session.paragraph.toLocaleString("en-GB")}. {progressLine(session)}.
        </p>
        <div className="control">
          <label htmlFor={ids.section} className="control-label">
            Section
          </label>
          <select
            id={ids.section}
            className="select"
            value={section}
            onChange={(e) => {
              if (isLabelSection(e.target.value)) setSection(e.target.value);
            }}
            data-testid="label-section"
          >
            {LABEL_SECTIONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={ids.text} className="field-label">
            Paragraph
          </label>
          <p id={ids.textHelp} className="help">
            One paragraph. It is checked under the section&rsquo;s heading and never stored; only your verdicts are kept,
            in this browser.
          </p>
          <textarea
            id={ids.text}
            ref={textRef}
            className="input label-text"
            rows={6}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (problem) setProblem(null);
            }}
            spellCheck={false}
            aria-invalid={problem ? true : undefined}
            aria-describedby={[ids.textHelp, problem ? ids.problem : null].filter(Boolean).join(" ")}
            data-testid="label-paragraph"
          />
          {problem ? (
            <p id={ids.problem} className="field-problem" role="alert" data-testid="label-problem">
              {problem}
            </p>
          ) : null}
        </div>
        <div className="label-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void runCheck()}
            aria-disabled={phase === "checking" || undefined}
            data-testid="label-check"
          >
            {phase === "checking" ? (
              <>
                <span className="spinner" aria-hidden="true" />
                Checking…
              </>
            ) : (
              "Check this paragraph"
            )}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onNext} data-testid="label-next">
            Next paragraph
          </button>
        </div>
      </section>

      {error ? (
        <div className="notice notice-error" role="alert" data-testid="label-error">
          <p className="notice-title">{error.title}</p>
          <p className="notice-text">{error.message}</p>
          {error.retryable ? (
            <button type="button" className="btn btn-secondary" onClick={() => void runCheck()}>
              Try again
            </button>
          ) : null}
        </div>
      ) : null}

      {phase === "done" ? (
        <section className="label-results" aria-labelledby="label-results-title" data-testid="label-results">
          <h2 id="label-results-title" className="results-title">
            {cards.length === 1 ? "1 flag" : `${cards.length.toLocaleString("en-GB")} flags`}
          </h2>
          {cards.length === 0 ? (
            <p className="empty-line" data-testid="label-empty">
              Nothing was flagged in this paragraph. Paragraphs without flags are skipped: go to the next one.
            </p>
          ) : (
            <>
              <p className="help">
                {labelled} of {cards.length} labelled in this paragraph.
              </p>
              <div className="cards label-cards">
                {cards.map((s) => (
                  <LabelCard key={s.id} suggestion={s} verdict={verdictFor(s.id)} onVerdict={onVerdict} />
                ))}
              </div>
            </>
          )}
        </section>
      ) : null}

      <section className="panel label-export" aria-labelledby="label-export-title">
        <h2 id="label-export-title" className="panel-title">
          Your labels
        </h2>
        <p className="help">
          The file holds paragraph numbers, rule codes, categories, sections and your verdicts. No text: neither your
          paragraphs nor the flagged words.
        </p>
        <div className="label-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onExport}
            aria-disabled={session.labels.length === 0 || undefined}
            data-testid="label-export"
          >
            Export labels
          </button>
          {session.labels.length > 0 ? (
            <ConfirmDelete
              label="Start over…"
              title="Delete every label in this browser?"
              body="Export them first if you want to keep them. This can’t be undone."
              keepLabel="Keep them"
              confirmLabel="Delete them"
              busy={false}
              onConfirm={async () => {
                clearLabelStore();
                setChanged(EMPTY_SESSION);
                setSlots({});
              }}
              testId="label-clear"
            />
          ) : null}
        </div>
      </section>
    </div>
  );
}

function LabelCard({
  suggestion: s,
  verdict,
  onVerdict,
}: {
  suggestion: Suggestion;
  verdict: Verdict | null;
  onVerdict: (s: Suggestion, v: Verdict) => void;
}) {
  const meta = categoryMeta(s.category);
  const msgId = `lmsg-${s.id}`;
  const plain = (s.plain ?? "").trim() || s.why.trim();
  return (
    <article className={`card card-${meta.id} label-card`} aria-labelledby={msgId} data-testid="label-card" data-rule={s.rule_id}>
      <div className="card-head">
        <CategoryBadge category={meta.id} />
      </div>
      <p className="card-msg" id={msgId}>
        {s.message}
      </p>
      {s.text.trim() ? (
        <p className="card-quote">
          <span className="sr-only">Flagged text: </span>
          <q>{s.text.replace(/\s+/g, " ").trim()}</q>
        </p>
      ) : null}
      {plain ? <p className="card-plain">{plain}</p> : null}
      <p className="card-source">
        <span className="card-source-label">Source:</span> <cite>{s.source}</cite>
      </p>
      <div className="label-verdict" role="group" aria-label="Your verdict on this flag" aria-describedby={msgId}>
        {VERDICT_BUTTONS.map((v) => (
          <button
            key={v.id}
            type="button"
            className={`btn btn-compact label-verdict-btn${verdict === v.id ? " is-on" : ""}`}
            aria-pressed={verdict === v.id}
            onClick={() => onVerdict(s, v.id)}
            data-testid={`verdict-${v.id}`}
          >
            {v.label}
          </button>
        ))}
      </div>
    </article>
  );
}
