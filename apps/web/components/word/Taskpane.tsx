"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  MAX_WORD_PARAGRAPHS,
  type AnalyzeWordResponse,
  type DocumentType,
  type TierHealth,
  type WordSuggestion,
} from "@researchly/contract";
import { addWord, loadDocumentType, loadMode, loadSettings, muteRule, saveDocumentType, saveMode } from "@/lib/account";
import { loadKeepProgress, recordProgress } from "@/lib/progress";
import { getEngineAuth, signOut, useAuth } from "@/lib/auth";
import { ENGINE_URL, LOCAL_ENGINE_URL, reportProblemHref } from "@/lib/config";
import { analyzeWord, engineHealth } from "@/lib/engine";
import { clientError, type CheckError } from "@/lib/errors";
import { healthBanners } from "@/lib/health";
import { briefState, narrativeState } from "@/lib/profiles";
import { useProfileChoices } from "@/lib/registry";
import { useRuleScopes } from "@/lib/scope";
import {
  isChecklistPref,
  loadChecklistChoice,
  loadDocumentTypeChoice,
  loadEngineChoice,
  loadModeChoice,
  saveChecklistChoice,
  saveDocumentTypeChoice,
  saveEngineChoice,
  saveModeChoice,
  subscribeDocumentType,
  subscribeWordPrefs,
  type ChecklistPref,
  type EngineChoice,
  type ModeChoice,
} from "@/lib/prefs";
import {
  applyReplacement,
  officeApi,
  readParagraphs,
  readSelectionParagraph,
  restoreHistory,
  selectSpan,
  officeGlobal,
  waitForOffice,
  type HostStatus,
} from "@/lib/word/office";
import {
  checklistHelp,
  checklistLabel,
  checklistOptions,
  checklistState,
  useChecklistChoices,
} from "@/lib/word/checklist";
import {
  coverageSentences,
  heldBackSentence,
  sectionAround,
  sectionName,
  sectionSummary,
  sectionView,
  shownWordSuggestions,
  STALE_NOTE,
  staleAfterEdit,
  wordProfileLine,
  wordSummary,
  type SectionFocus,
} from "@/lib/word/view";
import { HealthBanner } from "../HealthBanner";
import { NarrativeMap } from "../NarrativeMap";
import { ProfileSelect } from "../ProfileSelect";
import { ReviewBrief } from "../ReviewBrief";
import { CodeSignIn } from "./CodeSignIn";
import { WordCard, type CardNote, type WordCardActions } from "./WordCard";
import { WordChecklist } from "./WordChecklist";
import { WordTabs, wordViewIds, type WordView } from "./WordTabs";

type Phase = "idle" | "reading" | "checking" | "done" | "error";

interface Checked {
  seq: number;
  data: AnalyzeWordResponse;
  engine: EngineChoice;
  /** "Check this section": the paragraphs around the cursor at check time. The whole document was still checked. */
  focus: SectionFocus | null;
  /** The reporting checklist this check asked for (S4c). */
  checklist: ChecklistPref;
}

type Problem = { title: string; message: string };
type AccountNote = { ok: boolean; text: string };

const REPORT_HREF = reportProblemHref("Researchly Word add-in: a problem");

function engineUrlFor(engine: EngineChoice): string {
  return engine === "local" ? LOCAL_ENGINE_URL : ENGINE_URL;
}

/** The "This computer" engine is not running: say how to start it, not "check your connection". */
function localDownError(e: CheckError): CheckError {
  if (e.kind !== "unreachable" && e.kind !== "timeout") return e;
  return {
    ...e,
    title: "Researchly is not running on this computer",
    message:
      "Start the local server (python3 server.py in Researchly's word-addin folder), then check again. Or switch to Researchly cloud under Settings below.",
  };
}

/** Document-wide checks only make sense on a complete draft, so the stage says what each one checks. */
const MODE_HELP = "Draft: check what you've written so far. Revise: check the finished manuscript.";

/**
 * The Word add-in's taskpane (S3). Reads the document through Office.js
 * (lib/word/office.ts), sends its paragraphs straight to the chosen engine
 * (lib/engine.ts), and shows the same explained cards as the web checker.
 * Nothing is written to the document unless the writer presses Apply on a
 * card, and then only that one span, as a tracked change where Word can.
 */
export function Taskpane() {
  const { auth } = useAuth();
  const accounts = auth.status !== "off";
  const signedIn = auth.status === "signed_in";

  const [host, setHost] = useState<HostStatus | null>(null);
  const storedEngine = useSyncExternalStore(subscribeWordPrefs, loadEngineChoice, () => null);
  const [chosenEngine, setChosenEngine] = useState<EngineChoice | null>(null);
  const engine: EngineChoice = chosenEngine ?? storedEngine ?? "cloud";
  const storedMode = useSyncExternalStore(subscribeWordPrefs, loadModeChoice, () => null);
  const [accountMode, setAccountMode] = useState<ModeChoice | null>(null);
  const [chosenMode, setChosenMode] = useState<ModeChoice | null>(null);
  const mode: ModeChoice = chosenMode ?? (signedIn ? accountMode : null) ?? storedMode ?? "revise";
  // The article type to check as (S4), resolved like the stage: this
  // session's choice, else the account's, else this computer's, else Auto.
  const storedType = useSyncExternalStore(subscribeDocumentType, loadDocumentTypeChoice, () => null);
  const [accountType, setAccountType] = useState<DocumentType | null>(null);
  const [chosenType, setChosenType] = useState<DocumentType | null>(null);
  const documentType: DocumentType = chosenType ?? (signedIn ? accountType : null) ?? storedType ?? "auto";
  const [typeNote, setTypeNote] = useState<string | null>(null);
  // The reporting checklist (S4c): this session's choice, else this computer's, else None.
  const storedChecklist = useSyncExternalStore(subscribeWordPrefs, loadChecklistChoice, () => null);
  const [chosenChecklist, setChosenChecklist] = useState<ChecklistPref | null>(null);
  const checklist: ChecklistPref = chosenChecklist ?? storedChecklist ?? "none";
  /** Suggestions, the reviewer's brief, the narrative map or the checklist: survives a re-check, never stored. */
  const [resultsView, setResultsView] = useState<WordView>("suggestions");
  const [showPreferences, setShowPreferences] = useState(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [checked, setChecked] = useState<Checked | null>(null);
  const [error, setError] = useState<CheckError | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [health, setHealth] = useState<{ engine: EngineChoice; tiers: TierHealth[] | null; reachable: boolean } | null>(null);
  const [notes, setNotes] = useState<Record<string, CardNote>>({});
  const [applied, setApplied] = useState<ReadonlySet<string>>(new Set());
  /** Cards an edit has made out of date (their paragraph changed, or an Apply ended unknown): no Apply until a re-check. */
  const [stale, setStale] = useState<ReadonlySet<string>>(new Set());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [wordBusy, setWordBusy] = useState(false);
  const [accountNote, setAccountNote] = useState<AccountNote | null>(null);
  const [modeNote, setModeNote] = useState<string | null>(null);
  const [view, setView] = useState<"main" | "sign-in">("main");
  /** The writer chose to see the whole document after a section check (no re-check needed). */
  const [showWhole, setShowWhole] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const ids = {
    mode: useId(),
    modeHelp: useId(),
    type: useId(),
    checklist: useId(),
    checklistHelp: useId(),
    tabs: useId(),
    sectionHelp: useId(),
    privacy: useId(),
    engine: useId(),
    prefs: useId(),
  };

  /* ---------- start-up: where are we running? ---------- */

  useEffect(() => {
    let live = true;
    void waitForOffice(officeGlobal()).then((h) => {
      restoreHistory();
      if (live) setHost(h);
    });
    return () => {
      live = false;
      abortRef.current?.abort();
    };
  }, []);

  // Which tiers the chosen engine is running, before any check (no text is sent).
  useEffect(() => {
    if (host?.status !== "word") return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15_000);
    void engineHealth(engineUrlFor(engine), ctrl.signal)
      .then((r) => setHealth({ engine, tiers: r.ok ? r.data.tiers : null, reachable: r.ok }))
      .catch(() => {
        /* aborted: the engine choice changed or the pane closed */
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [engine, host]);

  // Signed in: Draft/Revise comes from the account (shared with the website).
  useEffect(() => {
    if (!signedIn) return;
    let live = true;
    void loadMode().then((r) => {
      if (live && r.ok && r.data) setAccountMode(r.data);
    });
    return () => {
      live = false;
    };
  }, [signedIn]);

  // Signed in: the article type comes from the account too (shared with the website).
  useEffect(() => {
    if (!signedIn) return;
    let live = true;
    void loadDocumentType().then((r) => {
      if (live && r.ok && r.data) setAccountType(r.data);
    });
    return () => {
      live = false;
    };
  }, [signedIn]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  // Which rules read the whole document (the "Whole document" group of a
  // section view). From the cloud engine's registry, once; the local server
  // has none, so the built-in list applies there.
  const scopes = useRuleScopes(engine === "cloud" ? ENGINE_URL : null, checked !== null);
  // The article types' labels, from the same registry; the local server has none, so the ids stand in.
  const profiles = useProfileChoices(engine === "cloud" ? ENGINE_URL : null);
  // The reporting checklists' labels, from the same registry when it lists them; the built-in list otherwise.
  const checklists = useChecklistChoices(engine === "cloud" ? ENGINE_URL : null);

  /* ---------- checking ---------- */

  const runCheck = useCallback(
    async (opts?: {
      mode?: ModeChoice;
      showPreferences?: boolean;
      section?: boolean;
      documentType?: DocumentType;
      checklist?: ChecklistPref;
    }) => {
      const api = officeApi();
      if (runningRef.current || !api || host?.status !== "word") return;
      runningRef.current = true;
      const useMode = opts?.mode ?? mode;
      const useType = opts?.documentType ?? documentType;
      const useChecklist = opts?.checklist ?? checklist;
      const prefs = opts?.showPreferences ?? showPreferences;
      // A re-check (mute, stage change) keeps the current view: section or whole document.
      const wantSection = opts?.section ?? (checked?.focus !== null && checked?.focus !== undefined && !showWhole);
      const useEngine = engine;
      setError(null);
      setProblem(null);
      setPhase("reading");
      setAnnouncement("Reading the document…");
      try {
        // The whole document is always sent: document-wide checks need all of
        // it. "Check this section" only records where the cursor is.
        let cursor: number | null = null;
        if (wantSection) {
          try {
            cursor = await readSelectionParagraph(api);
          } catch {
            setProblem({ title: "Word did not say where the cursor is", message: "Nothing was sent. Click in the section you are working on, then check again." });
            setPhase(checked ? "done" : "idle");
            return;
          }
        }
        let paragraphs;
        try {
          paragraphs = await readParagraphs(api);
        } catch {
          setProblem({ title: "Word did not hand over the document", message: "Nothing was sent. Click in the document, then check again." });
          setPhase("error");
          return;
        }
        if (!paragraphs.some((p) => p.text.trim())) {
          setProblem({ title: "This document is empty", message: "Write or paste some text into the document, then check again." });
          setPhase(checked ? "done" : "idle");
          return;
        }
        if (paragraphs.length > MAX_WORD_PARAGRAPHS) {
          setProblem({
            title: "This document is too long to check at once",
            message: `Researchly reads up to ${MAX_WORD_PARAGRAPHS.toLocaleString("en-GB")} paragraphs at a time. Check one chapter per document.`,
          });
          setPhase(checked ? "done" : "idle");
          return;
        }

        // The local server has no accounts: the sign-in token never goes
        // there, but the account's muted rules do (a rule muted anywhere
        // stays muted everywhere).
        let disabledRules: string[] = [];
        if (useEngine === "local" && signedIn) {
          const s = await loadSettings();
          if (s.ok) disabledRules = s.data.disabled_rules;
        }

        const ctrl = new AbortController();
        abortRef.current = ctrl;
        setPhase("checking");
        setAnnouncement("Checking your document…");
        // The brief, the narrative map and the checklist are whole-document reads, so they are asked for in Revise only.
        const r = await analyzeWord(
          {
            paragraphs,
            showPreferences: prefs,
            mode: useMode,
            disabledRules,
            documentType: useType,
            review: useMode === "revise",
            narrative: useMode === "revise",
            checklist: useMode === "revise" && useChecklist !== "none" ? useChecklist : null,
            signal: ctrl.signal,
          },
          engineUrlFor(useEngine),
          useEngine === "local" ? null : getEngineAuth(),
        );
        if (r.ok) {
          const focus = cursor !== null ? sectionAround(paragraphs, cursor) : null;
          setChecked((prev) => ({ seq: (prev?.seq ?? 0) + 1, data: r.data, engine: useEngine, focus, checklist: useChecklist }));
          setShowWhole(false);
          setNotes({});
          setApplied(new Set());
          setStale(new Set());
          setActiveId(null);
          setPhase("done");
          const listed = shownWordSuggestions(r.data, prefs);
          setAnnouncement(focus ? sectionSummary(sectionView(listed, focus, scopes), focus) : wordSummary(listed.length));
          // Opt-in progress (S4c): rule counts and words only, never text, and only
          // when the writer switched it on. A local check stays on this computer.
          if (signedIn && useEngine === "cloud") {
            const data = r.data;
            void loadKeepProgress()
              .then((k) => (k.ok && k.data ? recordProgress(data, true) : null))
              .catch(() => undefined);
          }
        } else {
          setError(useEngine === "local" ? localDownError(r.error) : r.error);
          setPhase("error");
          setAnnouncement("");
        }
      } catch {
        if (abortRef.current?.signal.aborted) {
          setPhase(checked ? "done" : "idle");
          setAnnouncement("Check cancelled.");
        } else {
          setError(clientError());
          setPhase("error");
        }
      } finally {
        runningRef.current = false;
        abortRef.current = null;
      }
    },
    [host, mode, documentType, checklist, showPreferences, engine, signedIn, checked, showWhole, scopes],
  );

  const onTypeChange = (next: DocumentType) => {
    if (next === documentType) return;
    setChosenType(next);
    saveDocumentTypeChoice(next);
    setTypeNote(null);
    if (signedIn) {
      void saveDocumentType(next).then((r) => {
        if (r.ok) setAccountType(next);
        else setTypeNote(`This choice could not be saved to your account, so it applies on this computer only. ${r.message}`);
      });
    }
    if (checked) void runCheck({ documentType: next });
  };

  const onChecklistChange = (next: ChecklistPref) => {
    if (next === checklist) return;
    setChosenChecklist(next);
    saveChecklistChoice(next);
    // Like a changed type: a check on screen is checked again, in Revise only (Draft never asks for it).
    if (checked && mode === "revise") void runCheck({ checklist: next });
  };

  const onModeChange = (next: ModeChoice) => {
    if (next === mode) return;
    setChosenMode(next);
    saveModeChoice(next);
    setModeNote(null);
    if (signedIn) {
      void saveMode(next).then((r) => {
        if (r.ok) setAccountMode(next);
        else setModeNote(`${next === "draft" ? "Draft" : "Revise"} could not be saved to your account, so it applies on this computer only. ${r.message}`);
      });
    }
    if (checked) void runCheck({ mode: next });
  };

  const onEngineChange = (next: EngineChoice) => {
    setChosenEngine(next);
    saveEngineChoice(next);
    setError(null);
  };

  const onRevealPreferences = () => {
    setShowPreferences(true);
    if (checked && checked.data.hidden_preferences > 0) void runCheck({ showPreferences: true });
  };

  /* ---------- in the document ---------- */

  const note = (id: string, n: CardNote | null) =>
    setNotes((prev) => {
      const next = { ...prev };
      if (n) next[id] = n;
      else delete next[id];
      return next;
    });

  const onSelect = useCallback(async (s: WordSuggestion) => {
    const api = officeApi();
    if (!api) return;
    setActiveId(s.id);
    setWordBusy(true);
    const r = await selectSpan(api, s.location);
    setWordBusy(false);
    if (!r.ok) note(s.id, { tone: "problem", text: r.message });
    else if (r.approximate) {
      note(s.id, {
        tone: "info",
        text: "The match is approximate: this passage is too long for Word to find whole, so only its start is selected.",
      });
    } else note(s.id, null);
  }, []);

  const onApply = useCallback(
    async (s: WordSuggestion) => {
      const api = officeApi();
      if (!api || s.replacement === null || s.replacement === undefined) return;
      setActiveId(s.id);
      setWordBusy(true);
      const r = await applyReplacement(api, s.location, s.replacement);
      setWordBusy(false);
      if (r.outcome === "not_applied") {
        note(s.id, { tone: "problem", text: r.message });
        return;
      }
      // Applied, or perhaps applied: the paragraph's other suggestions may have
      // moved. They lose Apply until a re-check (Codex review R3), and say why.
      const others = staleAfterEdit(checked?.data.suggestions ?? [], s.location.paragraph, s.id);
      setStale((prev) => {
        const next = new Set(prev);
        for (const id of others) next.add(id);
        if (r.outcome === "unknown") next.add(s.id);
        return next;
      });
      setNotes((prev) => {
        const next = { ...prev };
        for (const id of others) if (!next[id] || next[id]!.tone !== "problem") next[id] = { tone: "info", text: STALE_NOTE };
        return next;
      });
      if (r.outcome === "unknown") {
        note(s.id, { tone: "problem", text: r.message });
        return;
      }
      setApplied((prev) => new Set(prev).add(s.id));
      if (r.outcome === "restore_failed") {
        note(s.id, { tone: "problem", text: r.message });
        return;
      }
      note(s.id, {
        tone: "ok",
        text: r.tracked
          ? "Applied as a tracked change. Accept or reject it in Word's Review tab."
          : "Applied as a direct edit: this version of Word can't track it. Undo with Ctrl+Z (Cmd+Z on a Mac).",
      });
    },
    [checked],
  );

  /* ---------- account actions (signed in) ---------- */

  const onMute = useCallback(
    async (s: WordSuggestion) => {
      setAccountNote(null);
      const r = await muteRule(s.rule_id);
      if (!r.ok) {
        setAccountNote({ ok: false, text: r.message });
        return;
      }
      setAccountNote({ ok: true, text: `Muted “${s.rule_name}”. It stays muted in Word and on the website. Unmute it in the website's Settings.` });
      void runCheck();
    },
    [runCheck],
  );

  const onAddWord = useCallback(
    async (_s: WordSuggestion, word: string) => {
      setAccountNote(null);
      const r = await addWord(word);
      if (!r.ok) {
        setAccountNote({ ok: false, text: r.message });
        return;
      }
      setAccountNote({ ok: true, text: `Added “${word}” to your dictionary.` });
      void runCheck();
    },
    [runCheck],
  );

  const cardActions = useMemo<WordCardActions | null>(() => (signedIn ? { onMute, onAddWord } : null), [signedIn, onMute, onAddWord]);

  /* ---------- render ---------- */

  const busy = phase === "reading" || phase === "checking";
  const inWord = host?.status === "word";
  const shown = checked ? shownWordSuggestions(checked.data, showPreferences) : [];
  const focus = checked && !showWhole ? checked.focus : null;
  const split = focus ? sectionView(shown, focus, scopes) : { inSection: shown, wholeDocument: [], elsewhere: 0 };
  const listed = split.inSection.length + split.wholeDocument.length;
  const hiddenPrefs = checked
    ? checked.data.hidden_preferences + (showPreferences ? 0 : checked.data.suggestions.filter((s) => s.category === "preference").length)
    : 0;
  const heldBack = checked && checked.data.mode === "draft" ? heldBackSentence(checked.data.hidden_by_mode) : null;
  const coverage = checked ? coverageSentences(checked.data.coverage) : null;
  // After a check, its own report of the tiers; before, the engine's health.
  const tiers = checked && checked.engine === engine ? checked.data.health : health?.engine === engine ? health.tiers : null;
  const localDown = engine === "local" && health?.engine === "local" && !health.reachable;
  const suggestedChecklist = checked ? checklistLabel(checklists, checked.data.suggested_checklist) : null;
  // The Checklist tab: when this check asked for one, or one came back.
  const checklistTab = Boolean(checked && (checked.checklist !== "none" || checked.data.checklist));
  const shownView: WordView = resultsView === "checklist" && !checklistTab ? "suggestions" : resultsView;
  const profileText = checked ? wordProfileLine(checked.data.profile) : null;

  const wordCard = (s: WordSuggestion) => (
    <WordCard
      key={`${checked?.seq ?? 0}-${s.id}`}
      suggestion={s}
      active={activeId === s.id}
      applied={applied.has(s.id)}
      stale={stale.has(s.id)}
      note={notes[s.id] ?? null}
      busy={wordBusy || busy}
      onSelect={onSelect}
      onApply={onApply}
      actions={cardActions}
    />
  );

  const header = (
    <header className="tp-header">
      <p className="brand tp-brand" translate="no">
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="brand-mark">
          <path d="M5 4.5h9.5a4.5 4.5 0 010 9H9.5L15 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5 4.5V20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        Researchly
      </p>
      {accounts && view === "main" ? (
        auth.status === "loading" ? (
          <span className="tp-account-placeholder" aria-hidden="true" />
        ) : signedIn ? (
          <span className="tp-account" data-testid="tp-account">
            <span className="sr-only">Signed in as </span>
            <span className="tp-account-email break-anywhere">{auth.email}</span>
          </span>
        ) : (
          <button type="button" className="btn btn-quiet btn-compact" onClick={() => setView("sign-in")} data-testid="tp-sign-in">
            Sign in
          </button>
        )
      ) : null}
    </header>
  );

  const footer = (
    <footer className="tp-footer">
      <p>
        <a className="inline-link" href={REPORT_HREF} data-testid="report-problem">
          Report a problem
        </a>{" "}
        <span className="muted">by email. Please describe what happened; don&rsquo;t paste text from your document.</span>
      </p>
    </footer>
  );

  if (view === "sign-in" && accounts) {
    return (
      <div className="tp">
        {header}
        <main className="tp-main" id="main">
          <CodeSignIn
            onDone={(email) => {
              setView("main");
              setAnnouncement(`Signed in as ${email}.`);
            }}
            onCancel={() => setView("main")}
          />
        </main>
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {announcement}
        </div>
        {footer}
      </div>
    );
  }

  return (
    <div className="tp">
      {header}
      <main className="tp-main" id="main">
        <h1 className="sr-only">Researchly for Word</h1>

        {host === null ? (
          <p className="muted tp-connecting" role="status">
            Connecting to Word…
          </p>
        ) : !inWord ? (
          <section className="panel tp-outside" data-testid="not-in-word">
            <h2 className="panel-title">
              {host.status === "not_word" ? "Open Researchly from Word" : "Word’s add-in library did not load"}
            </h2>
            {host.status === "not_word" ? (
              <p>
                This page is Researchly&rsquo;s add-in for Microsoft Word. In Word, open it from the ribbon: Home, then
                Add-ins, then Researchly. To check pasted text instead, use <Link className="inline-link" href="/">the checker</Link>.
              </p>
            ) : (
              <p>Check your connection, then close and reopen the Researchly add-in. Nothing was read or sent.</p>
            )}
          </section>
        ) : (
          <>
            <section className="panel tp-check" aria-label="Check the document">
              <fieldset className="tp-mode" aria-describedby={ids.modeHelp}>
                <legend className="control-label">Stage</legend>
                <div className="segmented">
                  {(["draft", "revise"] as const).map((m) => (
                    <label key={m} className={`segment${mode === m ? " is-on" : ""}`}>
                      <input
                        type="radio"
                        name={ids.mode}
                        value={m}
                        checked={mode === m}
                        onChange={() => onModeChange(m)}
                        data-testid={`mode-${m}`}
                      />
                      <span>{m === "draft" ? "Draft" : "Revise"}</span>
                    </label>
                  ))}
                </div>
                <p id={ids.modeHelp} className="help" data-testid="mode-help">
                  {MODE_HELP}
                </p>
                {modeNote ? (
                  <p className="field-problem" role="alert" data-testid="mode-note">
                    {modeNote}
                  </p>
                ) : null}
              </fieldset>

              <ProfileSelect id={ids.type} value={documentType} choices={profiles} onChange={onTypeChange} note={typeNote} />

              <div className="control tp-checklist">
                <label htmlFor={ids.checklist} className="control-label">
                  Reporting checklist
                </label>
                <select
                  id={ids.checklist}
                  className="select"
                  value={checklist}
                  aria-describedby={ids.checklistHelp}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (isChecklistPref(v)) onChecklistChange(v);
                  }}
                  data-testid="checklist-select"
                >
                  {checklistOptions(checklists).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <p id={ids.checklistHelp} className="help control-help" data-testid="checklist-help">
                  {checklistHelp(checklists, checklist)}
                  {checklist === "none" && suggestedChecklist ? ` Your text's words point to ${suggestedChecklist}.` : ""}
                </p>
              </div>

              <div className="tp-row">
                <button
                  type="button"
                  className="btn btn-primary tp-check-btn"
                  onClick={() => void runCheck({ section: false })}
                  aria-disabled={busy || undefined}
                  aria-describedby={ids.privacy}
                  data-testid="check-document"
                >
                  {busy ? (
                    <>
                      <span className="spinner" aria-hidden="true" />
                      {phase === "reading" ? "Reading…" : "Checking…"}
                    </>
                  ) : checked ? (
                    "Check again"
                  ) : (
                    "Check document"
                  )}
                </button>
                {phase === "checking" ? (
                  <button type="button" className="btn btn-quiet" onClick={() => abortRef.current?.abort()}>
                    Cancel
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary tp-check-btn"
                    onClick={() => void runCheck({ section: true })}
                    aria-disabled={busy || undefined}
                    aria-describedby={ids.sectionHelp}
                    data-testid="check-section"
                  >
                    Check this section
                  </button>
                )}
              </div>
              <p id={ids.sectionHelp} className="help tp-section-help">
                &ldquo;Check this section&rdquo; still checks the whole document, then shows the section your cursor is in.
              </p>
              <p id={ids.privacy} className="privacy-line" data-testid="privacy-line">
                <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M5.5 7V5a2.5 2.5 0 015 0v2" fill="none" stroke="currentColor" strokeWidth="1.4" />
                </svg>
                {engine === "local"
                  ? "Checked on this computer. Nothing is sent over the network."
                  : "Analysed in memory and never stored. Nothing in the document changes unless you apply a revision."}
              </p>
            </section>

            {localDown && !error ? (
              <div className="notice notice-health" role="status" data-testid="local-down">
                <div>
                  <p className="notice-title">Researchly is not running on this computer</p>
                  <p className="notice-text">
                    Start the local server (python3 server.py in Researchly&rsquo;s word-addin folder), or switch to
                    Researchly cloud under Settings below.
                  </p>
                </div>
              </div>
            ) : null}

            {tiers && healthBanners(tiers).length > 0 ? <HealthBanner health={tiers} /> : null}

            {problem ? (
              <div className="notice notice-quiet" role="alert" data-testid="tp-problem">
                <p className="notice-title">{problem.title}</p>
                <p className="notice-text">{problem.message}</p>
              </div>
            ) : null}

            {error ? (
              <div ref={errorRef} className="notice notice-error" role="alert" tabIndex={-1} data-testid="tp-error" data-kind={error.kind}>
                <p className="notice-title">{error.title}</p>
                <p className="notice-text">{error.message}</p>
                {error.requestId ? (
                  <p className="notice-text">
                    <span className="notice-label">Reference:</span> <code className="request-id">{error.requestId}</code>
                  </p>
                ) : null}
                <div className="tp-row">
                  {error.retryable ? (
                    <button type="button" className="btn btn-secondary" onClick={() => void runCheck()} data-testid="tp-retry">
                      Try again
                    </button>
                  ) : null}
                  {error.signIn && accounts && !signedIn ? (
                    <button type="button" className="btn btn-secondary" onClick={() => setView("sign-in")} data-testid="tp-error-sign-in">
                      Sign in
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {accountNote ? (
              <div className={`notice ${accountNote.ok ? "notice-quiet" : "notice-error"}`} role={accountNote.ok ? "status" : "alert"} data-testid="account-note">
                <p className="notice-text">{accountNote.text}</p>
              </div>
            ) : null}

            {busy && !checked ? (
              <div className="loading-card" aria-hidden="true">
                <div className="skeleton" />
                <div className="skeleton short" />
              </div>
            ) : null}

            {checked ? (
              <section className="tp-results" aria-labelledby="tp-results-title" aria-busy={busy || undefined} data-testid="tp-results">
                <h2 id="tp-results-title" className="results-title">
                  {listed === 1 ? "1 suggestion" : `${listed.toLocaleString("en-GB")} suggestions`}
                  {focus ? ` in ${sectionName(focus)}` : ""}
                </h2>
                <p className="muted tp-results-meta">
                  {checked.data.mode === "draft" ? "Draft" : "Revise"}
                  {checked.engine === "local" ? ", checked on this computer" : ""}. Click a suggestion to find it in the document.
                </p>
                {profileText ? (
                  <p className="profile-line muted" data-testid="profile-line">
                    {profileText}
                  </p>
                ) : null}
                <WordTabs view={shownView} onChange={setResultsView} idBase={ids.tabs} checklist={checklistTab} />
                {shownView === "checklist" ? (
                  <div
                    role="tabpanel"
                    id={wordViewIds(ids.tabs, "checklist").panel}
                    aria-labelledby={wordViewIds(ids.tabs, "checklist").tab}
                    className="view-panel"
                    data-testid="checklist-panel"
                  >
                    <WordChecklist state={checklistState(checked.data, checked.checklist)} onSwitchToRevise={() => onModeChange("revise")} />
                  </div>
                ) : shownView === "brief" ? (
                  <div
                    role="tabpanel"
                    id={wordViewIds(ids.tabs, "brief").panel}
                    aria-labelledby={wordViewIds(ids.tabs, "brief").tab}
                    className="view-panel"
                    data-testid="brief-panel"
                  >
                    <ReviewBrief state={briefState(checked.data)} onSwitchToRevise={() => onModeChange("revise")} />
                  </div>
                ) : shownView === "narrative" ? (
                  <div
                    role="tabpanel"
                    id={wordViewIds(ids.tabs, "narrative").panel}
                    aria-labelledby={wordViewIds(ids.tabs, "narrative").tab}
                    className="view-panel"
                    data-testid="narrative-panel"
                  >
                    <NarrativeMap state={narrativeState(checked.data)} onSwitchToRevise={() => onModeChange("revise")} />
                  </div>
                ) : (
                  <div
                    role="tabpanel"
                    id={wordViewIds(ids.tabs, "suggestions").panel}
                    aria-labelledby={wordViewIds(ids.tabs, "suggestions").tab}
                    className="view-panel tp-suggestions"
                  >
                    <div className="tp-notes">
                      {focus ? (
                        <p className="tp-note" data-testid="section-focus">
                          Showing the section at the cursor, {sectionName(focus)}. The whole document was checked
                          {split.elsewhere > 0
                            ? `; ${split.elsewhere === 1 ? "1 more suggestion is" : `${split.elsewhere.toLocaleString("en-GB")} more suggestions are`} elsewhere in it.`
                            : "."}{" "}
                          <button type="button" className="btn-link" onClick={() => setShowWhole(true)} data-testid="show-whole-document">
                            Show the whole document
                          </button>
                        </p>
                      ) : null}
                      {heldBack ? (
                        <p className="tp-note" data-testid="held-back">
                          {heldBack}{" "}
                          <button type="button" className="btn-link" onClick={() => onModeChange("revise")}>
                            Switch to Revise
                          </button>
                        </p>
                      ) : null}
                      {hiddenPrefs > 0 ? (
                        <p className="tp-note" data-testid="hidden-prefs">
                          {hiddenPrefs === 1 ? "1 preference is hidden" : `${hiddenPrefs} preferences are hidden`}: matters of taste.{" "}
                          <button type="button" className="btn-link" onClick={onRevealPreferences}>
                            Show {hiddenPrefs === 1 ? "it" : "them"}
                          </button>
                        </p>
                      ) : null}
                      {coverage ? (
                        <p className="tp-note" data-testid="coverage">
                          {coverage.checked} {coverage.notChecked}
                        </p>
                      ) : null}
                    </div>
                    {split.inSection.length === 0 ? (
                      <div className="empty" data-testid="tp-empty">
                        <p className="empty-title">{focus ? "Nothing to flag in this section" : "Nothing to flag"}</p>
                        <p className="muted">
                          {focus ? `No suggestions in ${sectionName(focus)}. ` : "No suggestions for the parts that were checked. "}This is not a score.
                        </p>
                      </div>
                    ) : (
                      <div className="cards tp-cards">{split.inSection.map(wordCard)}</div>
                    )}
                    {split.wholeDocument.length > 0 ? (
                      <section className="card-group" aria-labelledby="tp-whole-document-title" data-testid="whole-document">
                        <h3 id="tp-whole-document-title" className="col-title card-group-title">
                          Whole document
                        </h3>
                        <p className="help card-group-help">
                          Checks that read the whole text, such as figure references and abbreviations defined once.
                        </p>
                        <div className="cards tp-cards">{split.wholeDocument.map(wordCard)}</div>
                      </section>
                    ) : null}
                  </div>
                )}
              </section>
            ) : null}

            <details className="panel tp-settings" data-testid="tp-settings">
              <summary>Settings</summary>
              <div className="tp-settings-body">
                <fieldset className="tp-engine">
                  <legend className="field-label">Checking engine</legend>
                  <label className="radio tp-radio">
                    <input
                      type="radio"
                      name={ids.engine}
                      value="cloud"
                      checked={engine === "cloud"}
                      onChange={() => onEngineChange("cloud")}
                      data-testid="engine-cloud"
                    />
                    <span>
                      <span className="tp-radio-title">Researchly cloud</span>
                      <span className="help">Analysed in memory, never stored, logged or used for training.</span>
                    </span>
                  </label>
                  <label className="radio tp-radio">
                    <input
                      type="radio"
                      name={ids.engine}
                      value="local"
                      checked={engine === "local"}
                      onChange={() => onEngineChange("local")}
                      data-testid="engine-local"
                    />
                    <span>
                      <span className="tp-radio-title">This computer</span>
                      <span className="help">
                        Nothing leaves your computer. Needs Researchly&rsquo;s local server running (python3 server.py).
                      </span>
                    </span>
                  </label>
                </fieldset>

                <label className="control control-toggle" htmlFor={ids.prefs}>
                  <input
                    id={ids.prefs}
                    type="checkbox"
                    role="switch"
                    className="switch"
                    checked={showPreferences}
                    onChange={(e) => setShowPreferences(e.target.checked)}
                    data-testid="tp-show-preferences"
                  />
                  <span>Show preferences</span>
                </label>

                {accounts ? (
                  <div className="tp-account-settings">
                    {signedIn ? (
                      <>
                        <p>
                          Signed in as <strong className="break-anywhere">{auth.email}</strong>. Muted rules and your
                          dictionary are managed in the website&rsquo;s Settings.
                        </p>
                        <button type="button" className="btn btn-quiet btn-compact" onClick={() => void signOut()} data-testid="tp-sign-out">
                          Sign out
                        </button>
                      </>
                    ) : (
                      <p className="muted">
                        Sign in to mute rules and keep a dictionary that follow you between Word and the website.
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            </details>
          </>
        )}
      </main>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="tp-announcer">
        {announcement}
      </div>
      {footer}
    </div>
  );
}
