/**
 * Engine responses for the mocked e2e runs. Each is a typed object that
 * `satisfies` the contract, so a contract change breaks the build of the
 * tests instead of silently drifting.
 */
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ChecklistChoiceInfo,
  ChecklistReport,
  DocumentType,
  ErrorResponse,
  NarrativeMap,
  ProfileChoice,
  ProfileInfo,
  ReviewReport,
  RuleInfo,
  Suggestion,
  TierHealth,
} from "@researchly/contract";
import { SAMPLE_SUGGESTIONS, SAMPLE_TEXT } from "./sample";

export { SAMPLE_TEXT };

export const ENGINE = "http://127.0.0.1:8099";

const healthy: TierHealth[] = [
  { tier: "parser", label: "Parser", ok: true, state: "ready", detail: "spaCy en_core_web_sm", remedy: "" },
  { tier: "spelling", label: "Spelling", ok: true, state: "ready", detail: "SymSpell + scientific lexicon", remedy: "" },
  { tier: "grammar", label: "Grammar", ok: true, state: "ready", detail: "LanguageTool sidecar", remedy: "" },
  // Missing learned tier is normal in this build and must NOT produce a banner.
  {
    tier: "gec",
    label: "Learned corrections",
    ok: false,
    state: "missing",
    detail: "no local model in this build (the tier abstains entirely)",
    remedy: "",
  },
];

const metrics = {
  sentences: 9,
  words: 74,
  mean_sentence_len: 8.2,
  long_sentences: 0,
  nominalizations_per_100w: 2.7,
  hedges_per_100w: 4.05,
  boosters_per_100w: 2.7,
  self_mention_per_100w: 1.35,
  hedge_booster_balance: "balanced (1.5:1)",
  passive_share_by_section: { methods: 0.67, discussion: 0.0 },
} satisfies AnalyzeResponse["metrics"];

const engine = { service_version: "0.1.0", core_version: "0.8.0", rules_loaded: 87 } satisfies AnalyzeResponse["engine"];

function countsOf(list: Suggestion[]): Record<string, number> {
  const c: Record<string, number> = {};
  for (const s of list) c[s.category] = (c[s.category] ?? 0) + 1;
  return c;
}

/**
 * The Learn card each sample rule's suggestions point to (S4: every
 * suggestion's `learn_ref` names a card). V305 is left without one, as an
 * older engine would send it, so the card without a lesson stays covered.
 */
export const SAMPLE_LEARN_REFS: Record<string, string | null> = {
  C201: "overclaiming",
  P110: "plain-words",
  V305: null,
  V310: "spelling-and-grammar",
  G110: "spelling-and-grammar",
  C120: "concise-words",
  S010: "spelling-and-grammar",
  D401: "discussion",
  C205: "hedging",
  P120: "concise-words",
};

const LEARNED_SUGGESTIONS: Suggestion[] = SAMPLE_SUGGESTIONS.map((s) => ({ ...s, learn_ref: SAMPLE_LEARN_REFS[s.rule_id] ?? null }));

const withoutPrefs = LEARNED_SUGGESTIONS.filter((s) => s.category !== "preference");
const prefsOnly = LEARNED_SUGGESTIONS.filter((s) => s.category === "preference");

/* ---------- S4: article types and the reviewer's brief ---------- */

/** GET /v1/rules `profiles`, as the engine lists them (packages/core/researchly/profiles.py), in display order. */
export const PROFILES: ProfileChoice[] = [
  { id: "auto", label: "Auto", summary: "Guess from the headings; otherwise general." },
  { id: "general", label: "General", summary: "Any research prose: every check on, sections from the headings." },
  { id: "manuscript", label: "Research article", summary: "A journal article with introduction, methods, results and discussion." },
  { id: "thesis-chapter", label: "Thesis chapter", summary: "One chapter of a thesis; sections as the chapter has them." },
  { id: "abstract", label: "Abstract", summary: "An abstract on its own: the six-move check runs on the whole text." },
  { id: "commentary", label: "Commentary", summary: "An opinion or perspective piece: argued, not reported." },
  { id: "policy-brief", label: "Policy brief", summary: "Evidence for decision-makers: context, evidence, options, recommendations." },
  { id: "grant", label: "Grant proposal", summary: "Aims, background and approach for a funder." },
  { id: "response-to-reviewers", label: "Response to reviewers", summary: "Point-by-point replies; the manuscript's own checks do not apply." },
];

export const COMMENTARY_NOTE =
  "Checked as a commentary: it may argue assertively, so the hedging prompts are off; no research gap is expected; there is no abstract to judge.";

/**
 * The profile a check ran under, as the engine reports it for a requested
 * type ("auto" guesses from the sample's headings). `evidence` is the
 * headings an Auto guess rested on; empty by default, as an engine before
 * the Codex review's R2 fix sends it.
 */
export function profileFor(type: DocumentType | null | undefined, evidence = ""): ProfileInfo {
  if (!type || type === "auto") return { id: "manuscript", label: "Research article", guessed: true, note: "", evidence, rules_off: [] };
  const choice = PROFILES.find((p) => p.id === type)!;
  const commentary = type === "commentary";
  return {
    id: type,
    label: choice.label,
    guessed: false,
    note: commentary ? COMMENTARY_NOTE : "",
    evidence: "",
    rules_off: commentary ? ["AB801", "AB802", "C302", "C303", "D902"] : [],
  };
}

/** The headings the website's mocked engine says its Auto guess rested on (the sample's own). */
export const GUESS_EVIDENCE = "Methods, Discussion";

export const REVIEW_DISCLAIMER =
  "This brief points to what a critical reader would ask, from signals in the wording. It does not establish whether the science is sound.";

export const REVIEW_SOURCE =
  "M. Wallace & A. Wray (2016), Critical Reading and Writing for Postgraduates, 3rd ed., SAGE; Amriit's learnings from scientific-writing training (Researchly notes)";

/** The critical reader's brief for SAMPLE_TEXT. Synthetic; the evidence sentences are the sample's own. */
export const REVIEW: ReviewReport = {
  source: REVIEW_SOURCE,
  disclaimer: REVIEW_DISCLAIMER,
  sections: ["introduction", "methods", "discussion"],
  words: 74,
  questions: [
    {
      id: "A",
      status: "yours",
      question: "Why am I reading this?",
      verdict: "Yours to answer: what do you need from this document?",
      points: ["The brief below reads it as a sceptical reader would, from the evidence in the text alone."],
      evidence: [],
    },
    {
      id: "B",
      status: "not_detected",
      question: "What are the authors trying to achieve?",
      verdict: "No sentence says what this document sets out to answer.",
      points: ["Where does the reader learn what question this document answers? One sentence near the end of the introduction usually does it."],
      evidence: [],
    },
    {
      id: "C",
      status: "detected",
      question: "What are they claiming?",
      verdict: "1 causal claim the design must carry.",
      points: ["vector control reduces transmission"],
      evidence: ["It is clearly proven that vector control reduces transmission."],
    },
    {
      id: "D",
      status: "detected",
      question: "How convincing are the claims?",
      verdict: "3 things weaken the claims; see the points.",
      points: [
        "No gap statement found: the reader is not told what was missing before this work, so the demand for it is unstated.",
        "Calibration: balanced (1.5:1) (hedges 4.05 per 100 words against boosters 2.7).",
        "1 overclaiming verb such as 'prove' or 'conclusively': reserve strong verbs for strong evidence.",
        "No limitations section: the reviewer will supply the rebuttal instead.",
      ],
      evidence: [],
    },
    {
      id: "E",
      status: "not_detected",
      question: "What use can be made of this?",
      verdict: "No sentence says what a reader can do with this.",
      points: ["The ending never widens back out: say what should change in the field or in practice, and for whom."],
      evidence: ["This could potentially suggest seasonal forcing."],
    },
  ],
  top_rules: [
    { id: "S010", short: "Repeated word", count: 2 },
    { id: "C201", short: "Booster overclaims certainty", count: 1 },
  ],
};

/* ---------- S4b: the narrative map ---------- */

export const NARRATIVE_SOURCE =
  "J. M. Swales (1990), Genre Analysis, Cambridge University Press (the three moves of an introduction); M. Wallace & A. Wray (2016), Critical Reading and Writing for Postgraduates, 3rd ed., SAGE; The Craft of Scientific Writing (Researchly's founding guide)";

const MOVE_SOURCE = "J. M. Swales (1990), Genre Analysis, Cambridge University Press";
const LINK_SOURCE = "M. Wallace & A. Wray (2016), Critical Reading and Writing for Postgraduates, 3rd ed., SAGE; S. Toulmin (1958), The Uses of Argument";

/**
 * The narrative map for SAMPLE_TEXT. Synthetic: the questions, lessons and
 * frames are Researchly's own wording; the evidence sentences are the
 * sample's own. One move is out of order (the Discussion reads its meaning
 * after what should change), six are missing.
 */
export const NARRATIVE: NarrativeMap = {
  note: "6 expected moves are missing; each one below has a question and a frame to fill in.",
  profile: "manuscript",
  source: NARRATIVE_SOURCE,
  unmapped: [],
  sections: [
    {
      section: "introduction",
      label: "Introduction",
      sentences: 2,
      words: 19,
      present: 1,
      expected: 3,
      moves: [
        {
          id: "intro.territory",
          learn_ref: "introduction",
          label: "Why it matters",
          status: "present",
          question: "Does the opening say why this area matters?",
          plain: "A reader decides in the first lines whether the problem is worth their time. Say what is at stake before saying what you did.",
          frame: "“[Topic] is a major [burden / challenge / question] in [setting], because [consequence].”",
          source: MOVE_SOURCE,
          evidence: "Dengue 🦟 remains a major burden across South-East Asia.",
          note: "",
        },
        {
          id: "intro.gap",
          learn_ref: "introduction",
          label: "What is missing",
          status: "missing",
          question: "Does the Introduction say what is still unknown?",
          plain: "The gap is the reason the work exists. Without it, the reader cannot tell whether the question was worth asking.",
          frame: "“Although [what is known], little is known about [the specific unknown], so [the consequence of not knowing].”",
          source: MOVE_SOURCE,
          evidence: null,
          note: "",
        },
        {
          id: "intro.aim",
          learn_ref: "introduction",
          label: "What you set out to do",
          status: "missing",
          question: "Is there a sentence that says what this work set out to answer?",
          plain: "One sentence near the end of the Introduction tells the reader what to expect from the rest. Without it, every section has to be read to find out.",
          frame: "“We therefore set out to [determine / estimate / test] [the research question].”",
          source: MOVE_SOURCE,
          evidence: null,
          note: "",
        },
      ],
    },
    {
      section: "methods",
      label: "Methods",
      sentences: 4,
      words: 36,
      present: 2,
      expected: 2,
      moves: [
        {
          id: "methods.data",
          learn_ref: "methods-reporting",
          label: "The data",
          status: "present",
          question: "Does the Methods section say what data were used, and where they came from?",
          plain: "A reader judges the result by the data behind it. Say what was collected, from whom, and when.",
          frame: "“[Data] were collected from [source] between [start] and [end].”",
          source: MOVE_SOURCE,
          evidence: "Data was collected from 2019 to 2023 However the reporting delay varied.",
          note: "",
        },
        {
          id: "methods.analysis",
          learn_ref: "methods-reporting",
          label: "The analysis",
          status: "present",
          question: "Does the Methods section say how the data were analysed?",
          plain: "The analysis is what turns data into a finding. Name the model and what it was asked to do.",
          frame: "“[Outcome] was modelled with [method], with [key choice] because [reason].”",
          source: MOVE_SOURCE,
          evidence: "The samples were analysed using a renewal model.",
          note: "",
        },
      ],
    },
    {
      section: "discussion",
      label: "Discussion",
      sentences: 2,
      words: 19,
      present: 2,
      expected: 5,
      moves: [
        {
          id: "discussion.finding",
          learn_ref: "discussion",
          label: "The main finding, restated",
          status: "missing",
          question: "Does the Discussion open by restating the main finding?",
          plain: "The reader has just come through the Results. Open by saying, in one sentence, what they showed.",
          frame: "“In this study we found that [main finding].”",
          source: MOVE_SOURCE,
          evidence: null,
          note: "",
        },
        {
          id: "discussion.meaning",
          learn_ref: "discussion",
          label: "What it means",
          status: "out_of_order",
          question: "Does the Discussion say why the evidence supports the claims?",
          plain: "A claim needs a bridge to its evidence. Say what the finding suggests, and why the evidence supports it.",
          frame: "“This suggests that [claim], because [why the evidence supports it].”",
          source: MOVE_SOURCE,
          evidence: "This could potentially suggest seasonal forcing.",
          note: "Appears after what should change.",
        },
        {
          id: "discussion.prior",
          learn_ref: "discussion",
          label: "Against earlier work",
          status: "missing",
          question: "Does the Discussion compare the findings with earlier work?",
          plain: "A finding means more next to what was known before. Say whether it agrees, and if not, why.",
          frame: "“Our estimate is [consistent with / higher than] [earlier work], which [reason].”",
          source: MOVE_SOURCE,
          evidence: null,
          note: "",
        },
        {
          id: "discussion.limits",
          learn_ref: "discussion",
          label: "What this cannot show",
          status: "missing",
          question: "Does the Discussion state the limitations?",
          plain: "A limitation stated by the author is a boundary; one found by the reviewer is a rebuttal. State them first.",
          frame: "“This study has limitations. First, [constraint], which means [bounded consequence].”",
          source: MOVE_SOURCE,
          evidence: null,
          note: "",
        },
        {
          id: "discussion.implication",
          learn_ref: "discussion",
          label: "What should change",
          status: "present",
          question: "Does the ending say what a reader could do with this?",
          plain: "The ending widens back out: say what should change in the field or in practice, and for whom.",
          frame: "“[Decision-makers] could use this to [action], provided [condition].”",
          source: MOVE_SOURCE,
          evidence: "In order to understand the the dynamics of transmission, further studies are needed.",
          note: "",
        },
      ],
    },
  ],
  missing_links: [
    {
      section: "discussion",
      label: "Discussion",
      code: "claim_without_warrant",
      learn_ref: "warranting",
      evidence: ["This could potentially suggest seasonal forcing."],
      message:
        "1 claim-type sentence in the Discussion but no warrant signal (because, this suggests that, consistent with). The reader is given the claim but not why the evidence supports it.",
      source: LINK_SOURCE,
    },
    {
      section: "discussion",
      label: "Discussion",
      code: "claim_without_grounds",
      learn_ref: null,
      evidence: [],
      message: "A claim in the Discussion with no evidence signal (numbers, citations, reported findings) in the same section: what is it standing on?",
      source: LINK_SOURCE,
    },
  ],
  hedging: [
    { section: "introduction", label: "Introduction", words: 19, hedges_per_100w: 0, boosters_per_100w: 5.26, reading: "assertive" },
    { section: "methods", label: "Methods", words: 36, hedges_per_100w: 0, boosters_per_100w: 0, reading: "flat" },
    { section: "discussion", label: "Discussion", words: 19, hedges_per_100w: 10.53, boosters_per_100w: 0, reading: "heavily hedged" },
  ],
};

/** show_preferences: false — the engine withholds preferences and reports how many. */
export const happyResponse = {
  schema_version: "1",
  signed_in: false,
  warnings: [],
  suggestions: withoutPrefs,
  counts: countsOf(withoutPrefs),
  hidden_preferences: prefsOnly.length,
  metrics,
  sections_detected: ["introduction", "methods", "discussion"],
  health: healthy,
  engine,
  elapsed_ms: 412,
  mode: "revise",
  hidden_by_mode: 0,
  profile: profileFor("auto"),
  review: REVIEW,
  narrative: NARRATIVE,
  checklist: null,
  suggested_checklist: null,
} satisfies AnalyzeResponse;

/** show_preferences: true */
export const withPreferencesResponse = {
  ...happyResponse,
  suggestions: LEARNED_SUGGESTIONS,
  counts: countsOf(LEARNED_SUGGESTIONS),
  hidden_preferences: 0,
} satisfies AnalyzeResponse;

export const degradedGrammarResponse = {
  ...happyResponse,
  health: healthy.map((t) =>
    t.tier === "grammar"
      ? {
          ...t,
          ok: false,
          state: "error",
          detail: "LanguageTool did not respond in time",
          remedy: "Grammar checks return automatically once it recovers; check again in a minute",
        }
      : t,
  ),
} satisfies AnalyzeResponse;

export const emptyResponse = {
  ...happyResponse,
  suggestions: [],
  counts: {},
  hidden_preferences: 0,
} satisfies AnalyzeResponse;

export const error413 = {
  error: { code: "payload_too_large", message: "Document too large", request_id: "req-413-7d1c" },
} satisfies ErrorResponse;

export const error429 = {
  error: { code: "rate_limited", message: "Rate limited", request_id: "req-429-0b2e" },
} satisfies ErrorResponse;

export const error500 = {
  error: { code: "internal", message: "Engine error", request_id: "req-500-a9f3c2" },
} satisfies ErrorResponse;

export const error422 = {
  error: { code: "invalid_request", message: "format must be one of: plain, markdown, latex", request_id: "req-422-11aa" },
} satisfies ErrorResponse;

/** Code-point offset of `needle` in SAMPLE_TEXT (Python indices, as the engine counts). */
function cp(needle: string): number {
  const i = SAMPLE_TEXT.indexOf(needle);
  if (i < 0) throw new Error(`fixture needle not found: ${needle}`);
  return Array.from(SAMPLE_TEXT.slice(0, i)).length;
}

/** A document-wide suggestion (rule scope "document"): one spelling of a compound differs elsewhere. Synthetic. */
export const compoundSuggestion: Suggestion = {
  id: "e2e-compound-1",
  rule_id: "W211",
  rule_name: "Compound spelled two ways",
  category: "convention",
  tier: "craft",
  span: { start: cp("South-East"), end: cp("South-East") + "South-East".length, line: 2, col: 42 },
  section: "introduction",
  message: "‘South-East’ is also written ‘Southeast’ elsewhere in this text.",
  why: "A compound written two ways reads as two terms. Pick one spelling and use it throughout.",
  plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
  source: "The Craft of Scientific Writing §6",
  learn_ref: null,
  replacement: null,
  fix_safety: "review",
  confidence: 1,
  text: "South-East",
};

/** The happy response plus one document-wide suggestion (9 shown). */
export const withDocumentWideResponse = {
  ...happyResponse,
  suggestions: [...withoutPrefs, compoundSuggestion],
  counts: countsOf([...withoutPrefs, compoundSuggestion]),
} satisfies AnalyzeResponse;

/** GET /v1/rules, as the mocked engine answers it: scopes for the rules the fixtures use. */
export const RULES_REGISTRY: RuleInfo[] = ["C201", "P110", "V305", "V310", "G110", "C120", "S010", "D401", "C205", "P120", "W211"].map((id) => ({
  id,
  name: id,
  short: "A synthetic rule for the e2e suite.",
  why: "w",
  plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
  source: "s",
  category: "improvement",
  tier: "craft",
  fix_safety: "review",
  scope: id === "W211" ? "document" : "sentence",
}));

/* ---------- S4: reporting checklists ---------- */

/** GET /v1/rules `checklists`, as the engine lists them (packages/core/researchly/packs/). */
export const CHECKLISTS: ChecklistChoiceInfo[] = [
  { id: "strobe", label: "STROBE", design: "observational studies (cohort, case-control, cross-sectional)", pack: "Epidemiology" },
  { id: "consort", label: "CONSORT", design: "randomised controlled trials", pack: "Epidemiology" },
  { id: "prisma", label: "PRISMA", design: "systematic reviews and meta-analyses", pack: "Epidemiology" },
  { id: "epiforge", label: "EPIFORGE", design: "epidemic forecasts, projections and predictions", pack: "Epidemiology" },
];

export const CHECKLIST_SOURCE = "S. Pollett et al. (2021), the EPIFORGE 2020 guidelines for reporting epidemic forecasting and prediction research";

/**
 * A checklist report for SAMPLE_TEXT. Synthetic: the topics, questions and
 * reasons are Researchly's own wording; the one reported item quotes the
 * sample's own sentence. Two items need the writer's check.
 */
export const CHECKLIST: ChecklistReport = {
  id: "epiforge",
  label: "EPIFORGE",
  design: "epidemic forecasts, projections and predictions",
  source: CHECKLIST_SOURCE,
  suggested: false,
  reported: 1,
  total: 3,
  note: "1 of 3 items were found in the text. The others need your check: they may be reported in a table, a figure or the supplement, or not apply to this study. This checks reporting only, never the science.",
  items: [
    {
      id: "model",
      topic: "Model description",
      question: "Is the model described well enough to reproduce: its structure and type?",
      plain: "Readers need to know what produced the numbers.",
      sections: ["methods"],
      status: "reported",
      evidence: "The samples were analysed using a renewal model.",
    },
    {
      id: "horizon",
      topic: "Horizon",
      question: "Is the forecast horizon given (how far ahead)?",
      plain: "Accuracy falls with the horizon; readers need it to weigh any number.",
      sections: ["introduction", "methods"],
      status: "needs_check",
      evidence: null,
    },
    {
      id: "uncertainty",
      topic: "Uncertainty",
      question: "Are forecasts given with their uncertainty (intervals or quantiles)?",
      plain: "A point forecast without its range invites false confidence.",
      sections: ["results", "methods"],
      status: "needs_check",
      evidence: null,
    },
  ],
};

/** Pick the right success fixture for a request, as the real engine would: preferences, the profile asked for, the brief, the map and a checklist only when asked. */
export function responseFor(req: AnalyzeRequest): AnalyzeResponse {
  const base = req.options?.show_preferences ? withPreferencesResponse : happyResponse;
  const list = req.options?.checklist;
  return {
    ...base,
    profile: profileFor(req.options?.document_type, GUESS_EVIDENCE),
    review: req.options?.review ? REVIEW : null,
    narrative: req.options?.narrative ? NARRATIVE : null,
    checklist: list ? { ...CHECKLIST, suggested: list === "auto" } : null,
    suggested_checklist: null,
  };
}
