"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { RuleInfo } from "@researchly/contract";
import { openSignIn, useAuth } from "@/lib/auth";
import { ENGINE_URL } from "@/lib/config";
import { cardForRule, lessonHref } from "@/lib/learn";
import { deleteProgress, loadKeepProgress, loadProgress, type ProgressEvent } from "@/lib/progress";
import { formatRate, MIN_FIRES, ruleTrends, type RuleTrend } from "@/lib/progress-view";
import { useRegistry } from "@/lib/registry";
import { ConfirmDelete } from "./ConfirmDelete";
import { Sparkline } from "./Sparkline";

type Loaded = { keep: boolean; events: ProgressEvent[] };

/**
 * The personal progress view (S4c): opt-in, counts only. Per rule that fired
 * at least twice, its rate per 1,000 words in each recorded check as a small
 * multiple (one compact line per rule, oldest check on the left), with the
 * first and latest values written out and a word for the direction. Never a
 * score, a grade or a total: each rule's own line, nothing summed.
 */
export function Progress() {
  const { auth } = useAuth();
  if (auth.status === "loading" || auth.status === "off") {
    return (
      <div className="loading-card" aria-hidden="true">
        <div className="skeleton" />
        <div className="skeleton short" />
      </div>
    );
  }
  if (auth.status === "signed_out") {
    return (
      <section className="panel settings-gate" aria-labelledby="progress-gate-title" data-testid="progress-signed-out">
        <h2 id="progress-gate-title" className="panel-title">
          Sign in to see your progress
        </h2>
        <p className="muted">
          Progress is kept with your account, and only if you switch it on: how often each check fired, never your text.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => openSignIn()}>
          Sign in
        </button>
      </section>
    );
  }
  return <SignedInProgress key={auth.email} />;
}

function SignedInProgress() {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  // Rule names and lesson links come from the engine's registry (no text is sent).
  const registry = useRegistry(ENGINE_URL, true);

  useEffect(() => {
    let live = true;
    void Promise.all([loadKeepProgress(), loadProgress()]).then(([k, p]) => {
      if (!live) return;
      if (!k.ok || !p.ok) {
        setError(!k.ok ? k.message : !p.ok ? p.message : null);
        return;
      }
      setError(null);
      setLoaded({ keep: k.data, events: p.data });
    });
    return () => {
      live = false;
    };
  }, [reload]);

  const onDelete = async () => {
    const r = await deleteProgress();
    setStatus(r.ok ? { ok: true, text: "Your recorded progress was deleted." } : { ok: false, text: r.message });
    if (r.ok) setLoaded((l) => (l ? { ...l, events: [] } : l));
  };

  if (error) {
    return (
      <div className="notice notice-error" role="alert" data-testid="progress-load-error">
        <p className="notice-title">Your progress could not be loaded</p>
        <p className="notice-text">{error}</p>
        <button type="button" className="btn btn-secondary" onClick={() => setReload((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!loaded) {
    return (
      <div className="loading-card" aria-hidden="true" data-testid="progress-loading">
        <div className="skeleton" />
        <div className="skeleton short" />
      </div>
    );
  }

  const rules = new Map<string, RuleInfo>((registry?.rules ?? []).map((r) => [r.id, r]));
  const { checks, trends } = ruleTrends(loaded.events);
  const deleteControl =
    loaded.events.length > 0 ? (
      <div className="progress-delete">
        <ConfirmDelete
          label="Delete my progress…"
          title="Delete your recorded progress?"
          body="Every recorded check (rule counts and word counts) will be removed from your account. This can’t be undone."
          keepLabel="Keep it"
          confirmLabel="Delete it"
          busy={false}
          onConfirm={onDelete}
          testId="delete-progress"
        />
      </div>
    ) : null;

  return (
    <div className="progress" data-testid="progress">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="progress-status">
        {status?.ok ? status.text : ""}
      </div>
      {status && !status.ok ? (
        <div className="notice notice-error" role="alert">
          <p className="notice-text">{status.text}</p>
        </div>
      ) : null}

      {!loaded.keep ? (
        <section className="panel settings-section" aria-labelledby="progress-off-title" data-testid="progress-off">
          <h2 id="progress-off-title" className="panel-title">
            Progress is off
          </h2>
          <p className="section-intro">
            Researchly records nothing about your checks unless you ask it to. Switch on &ldquo;Keep my progress&rdquo;
            in <Link className="inline-link" href="/settings">Settings</Link> and, after each check, it records how many
            times each check fired and how many words were checked. Never your text.
          </p>
          {loaded.events.length > 0 ? (
            <p className="help">What was recorded before you switched it off stays until you delete it.</p>
          ) : null}
          {deleteControl}
        </section>
      ) : trends.length === 0 ? (
        <section className="panel settings-section" aria-labelledby="progress-empty-title" data-testid="progress-empty">
          <h2 id="progress-empty-title" className="panel-title">
            Nothing to show yet
          </h2>
          <p className="section-intro">
            A check appears here once it has fired at least {MIN_FIRES === 2 ? "twice" : `${MIN_FIRES} times`} across
            your recorded checks. Check a draft while signed in and come back.
          </p>
          {deleteControl}
        </section>
      ) : (
        <section className="progress-board" aria-labelledby="progress-board-title">
          <h2 id="progress-board-title" className="progress-board-title">
            How often each check fired, per 1,000 words
          </h2>
          <p className="help progress-board-help" data-testid="progress-help">
            Across your {checks === 1 ? "one recorded check" : `${checks.toLocaleString("en-GB")} recorded checks`}, oldest on
            the left. Each line runs from zero to its own highest value. A trajectory to notice, not a score: a draft
            with more figures or more claims will fire more checks.
          </p>
          <ul className="trend-list" data-testid="trend-list">
            {trends.map((t) => (
              <TrendRow key={t.ruleId} trend={t} rule={rules.get(t.ruleId) ?? null} checks={checks} />
            ))}
          </ul>
          <details className="progress-table" data-testid="progress-table">
            <summary>Every value, as a table</summary>
            <table className="progress-values">
              <caption className="sr-only">Flags per 1,000 words in each recorded check, oldest first</caption>
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col">Per 1,000 words, oldest first</th>
                </tr>
              </thead>
              <tbody>
                {trends.map((t) => (
                  <tr key={t.ruleId}>
                    <th scope="row">{nameOf(t.ruleId, rules.get(t.ruleId) ?? null)}</th>
                    <td>{t.rates.map(formatRate).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          {deleteControl}
        </section>
      )}
    </div>
  );
}

/** A rule's short name from the registry; its name or, failing both, a neutral phrase (codes are never shown). */
function nameOf(id: string, rule: RuleInfo | null): string {
  return rule?.short?.trim() || rule?.name?.trim() || "A check no longer in the engine";
}

function TrendRow({ trend: t, rule, checks }: { trend: RuleTrend; rule: RuleInfo | null; checks: number }) {
  const name = nameOf(t.ruleId, rule);
  const lesson = cardForRule(t.ruleId, rule?.learn_ref);
  const values =
    checks > 1
      ? `From ${formatRate(t.first)} to ${formatRate(t.latest)} per 1,000 words`
      : `${formatRate(t.latest)} per 1,000 words`;
  return (
    <li className="trend" data-testid="trend" data-rule={t.ruleId}>
      <p className="trend-name">{name}</p>
      <div className="trend-chart">
        <Sparkline rates={t.rates} label={`${name}: ${values.toLowerCase()}${t.word ? `, ${t.word}` : ""}.`} />
        <p className="trend-values" data-testid="trend-values">
          {values}
          {t.word ? (
            <>
              : <strong className="trend-word">{t.word}</strong>
            </>
          ) : null}
          .
        </p>
      </div>
      {lesson ? (
        <p className="trend-lesson">
          <span className="muted">Lesson: </span>
          <Link className="inline-link" href={lessonHref(lesson)}>
            {lesson.title}
          </Link>
        </p>
      ) : null}
    </li>
  );
}
