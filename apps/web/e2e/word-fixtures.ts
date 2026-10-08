/**
 * The Word add-in's e2e document and engine answers (S3). The document is
 * synthetic (written for these tests); responses are typed with
 * `satisfies` so a contract change breaks the tests' build, not their meaning.
 */
import type { Page, Route } from "@playwright/test";
import type {
  AnalyzeWordRequest,
  AnalyzeWordResponse,
  ChecklistReport,
  DocumentType,
  HealthResponse,
  NarrativeMap,
  ReviewReport,
  ProfileInfo,
  RuleInfo,
  TierHealth,
  WordSuggestion,
} from "@researchly/contract";
import { fakeOfficeScript, type FakeWordConfig, type FakeWordState } from "./fake-office";
import { NARRATIVE_SOURCE, profileFor, PROFILES, REVIEW_SOURCE } from "./fixtures";

export const OFFICE_JS = "https://appsforoffice.microsoft.com/lib/1/hosted/office.js";
export const LOCAL_ENGINE = "http://localhost:3517";

export const DOC: FakeWordConfig["paragraphs"] = [
  { text: "Methods", styleBuiltIn: "Heading1" },
  {
    text: "In order to estimate the effective reproduction number, a renewal model was fitted. The the priors were weakly informative for nowcasting.",
    styleBuiltIn: "Normal",
  },
  { text: "Discussion", styleBuiltIn: "Heading1" },
  { text: "It is clearly proven that the the effect of vector control was large, and the the data agree.", styleBuiltIn: "Normal" },
  { text: "Region", tableNestingLevel: 1 },
];

const OFFSETS = (() => {
  const out: number[] = [];
  let pos = 0;
  for (const p of DOC) {
    out.push(pos);
    pos += p.text.length + 2;
  }
  return out;
})();

/** Where match number `occurrence` of `needle` sits in paragraph `paragraph`. */
export function at(paragraph: number, needle: string, occurrence = 0): number {
  const text = DOC[paragraph]!.text;
  let i = -1;
  for (let n = 0; n <= occurrence; n++) {
    i = text.indexOf(needle, n === 0 ? 0 : i + needle.length);
    if (i < 0) throw new Error(`fixture: "${needle}" #${occurrence} not in paragraph ${paragraph}`);
  }
  return i;
}

function wsugg(
  id: string,
  paragraph: number,
  needle: string,
  occurrence: number,
  extra: Partial<WordSuggestion> & Pick<WordSuggestion, "rule_id" | "rule_name" | "message">,
  exact = true,
  spanLength = needle.length,
): WordSuggestion {
  const start = at(paragraph, needle, occurrence);
  const end = start + spanLength;
  const text = DOC[paragraph]!.text.slice(start, end);
  return {
    id,
    category: "improvement",
    tier: "craft",
    section: paragraph < 2 ? "methods" : "discussion",
    why: "A synthetic explanation for the e2e suite.",
    plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    source: "The Craft of Scientific Writing, §4",
    fix_safety: "review",
    confidence: 1,
    replacement: null,
    span: { start: OFFSETS[paragraph]! + start, end: OFFSETS[paragraph]! + end, line: 1, col: start + 1 },
    text,
    location: { paragraph, start, end, snippet: needle, occurrence, exact },
    learn_ref: null,
    ...extra,
  };
}

export const WORDY = wsugg("w-wordy", 1, "In order to", 0, {
  rule_id: "C120",
  rule_name: "Wordy phrase",
  message: "‘In order to’ can usually be ‘To’.",
  replacement: "To",
  fix_safety: "safe",
});
export const REPEAT_1 = wsugg("w-repeat-1", 1, "The the", 0, {
  rule_id: "S010",
  rule_name: "Repeated word",
  category: "correction",
  tier: "spelling",
  message: "‘the’ is repeated.",
  replacement: "The",
});
export const NOWCASTING = wsugg("w-spell", 1, "nowcasting", 0, {
  rule_id: "S001",
  rule_name: "Possible misspelling",
  category: "correction",
  tier: "spelling",
  message: "‘nowcasting’ is not in the dictionary.",
});
export const LONG = wsugg(
  "w-long",
  3,
  "It is clearly proven",
  0,
  {
    rule_id: "G106",
    rule_name: "Long sentence",
    message: "This sentence is long; consider splitting it.",
  },
  false,
  DOC[3]!.text.length,
);
export const BOOSTER = wsugg("w-booster", 3, "clearly proven", 0, {
  rule_id: "C201",
  rule_name: "Booster overclaims certainty",
  category: "convention",
  message: "‘clearly proven’ claims more certainty than the evidence can carry.",
});
export const REPEAT_2A = wsugg("w-repeat-2a", 3, "the the", 0, {
  rule_id: "S010",
  rule_name: "Repeated word",
  category: "correction",
  tier: "spelling",
  message: "‘the’ is repeated.",
  replacement: "the",
});
/** Document-wide (rule scope "document"): shown under "Whole document" in a section view. */
export const COMPOUND = wsugg("w-compound", 3, "vector control", 0, {
  rule_id: "W211",
  rule_name: "Compound spelled two ways",
  category: "convention",
  message: "‘vector control’ is also written ‘vector-control’ elsewhere in this document.",
});
export const REPEAT_2B = wsugg("w-repeat-2b", 3, "the the", 1, {
  rule_id: "S010",
  rule_name: "Repeated word",
  category: "correction",
  tier: "spelling",
  message: "‘the’ is repeated (second time in this sentence).",
  replacement: "the",
});

export const HEALTHY: TierHealth[] = [
  { tier: "parser", label: "Parser", ok: true, state: "ready", detail: "spaCy en_core_web_sm", remedy: "" },
  { tier: "spelling", label: "Spelling", ok: true, state: "ready", detail: "SymSpell", remedy: "" },
  { tier: "grammar", label: "Grammar", ok: true, state: "ready", detail: "LanguageTool", remedy: "" },
  { tier: "gec", label: "Learned corrections", ok: false, state: "missing", detail: "no local model", remedy: "" },
];

export const DEGRADED: TierHealth[] = HEALTHY.map((t) =>
  t.tier === "grammar"
    ? { ...t, ok: false, state: "error", detail: "LanguageTool did not respond in time", remedy: "Check again in a minute" }
    : t,
);

const ALL = [WORDY, REPEAT_1, NOWCASTING, LONG, BOOSTER, REPEAT_2A, COMPOUND, REPEAT_2B];
const SENTENCE_LEVEL = ALL.filter((s) => s.rule_id !== "W211");

/** GET /v1/rules from the cloud engine: the scopes of the rules above. */
export const WORD_RULES: RuleInfo[] = [...new Set(ALL.map((s) => s.rule_id))].map((id) => ({
  id,
  name: id,
  short: "A synthetic rule for the e2e suite.",
  why: "w",
  plain: "p",
  source: "s",
  category: "improvement",
  tier: "craft",
  fix_safety: "review",
  scope: id === "W211" ? "document" : "sentence",
}));

/** The critical reader's brief for DOC (S4). Synthetic; the evidence is the document's own sentence. */
export const WORD_REVIEW: ReviewReport = {
  source: REVIEW_SOURCE,
  disclaimer: "The brief reads the writing, not the science: it cannot tell whether the design or the analysis was right.",
  sections: ["methods", "discussion"],
  words: 38,
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
      status: "detected",
      question: "What are the authors trying to achieve?",
      verdict: "An aim is stated.",
      points: [],
      evidence: ["In order to estimate the effective reproduction number, a renewal model was fitted."],
    },
    {
      id: "C",
      status: "detected",
      question: "What are they claiming?",
      verdict: "1 causal claim the design must carry.",
      points: ["the effect of vector control was large"],
      evidence: ["It is clearly proven that the the effect of vector control was large, and the the data agree."],
    },
    {
      id: "D",
      status: "detected",
      question: "How convincing are the claims?",
      verdict: "2 things weaken the claims; see the points.",
      points: [
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
      evidence: [],
    },
  ],
  top_rules: [
    { id: "S010", short: "Repeated word", count: 4 },
    { id: "C120", short: "Wordy phrase", count: 1 },
  ],
};

const WORD_MOVE_SOURCE = "J. M. Swales (1990), Genre Analysis, Cambridge University Press";

/** The narrative map for DOC (S4b). Synthetic; the evidence sentences are the document's own. */
export const WORD_NARRATIVE: NarrativeMap = {
  note: "4 expected moves are missing; each one below has a question and a frame to fill in.",
  profile: "manuscript",
  source: NARRATIVE_SOURCE,
  unmapped: [],
  sections: [
    {
      section: "methods",
      label: "Methods",
      sentences: 2,
      words: 21,
      present: 1,
      expected: 2,
      moves: [
        {
          id: "methods.data",
          label: "The data",
          status: "missing",
          question: "Does the Methods section say what data were used, and where they came from?",
          plain: "A reader judges the result by the data behind it. Say what was collected, from whom, and when.",
          frame: "“[Data] were collected from [source] between [start] and [end].”",
          source: WORD_MOVE_SOURCE,
          evidence: null,
          note: "",
          learn_ref: null,
        },
        {
          id: "methods.analysis",
          label: "The analysis",
          status: "present",
          question: "Does the Methods section say how the data were analysed?",
          plain: "The analysis is what turns data into a finding. Name the model and what it was asked to do.",
          frame: "“[Outcome] was modelled with [method], with [key choice] because [reason].”",
          source: WORD_MOVE_SOURCE,
          evidence: "In order to estimate the effective reproduction number, a renewal model was fitted.",
          note: "",
          learn_ref: null,
        },
      ],
    },
    {
      section: "discussion",
      label: "Discussion",
      sentences: 1,
      words: 17,
      present: 1,
      expected: 4,
      moves: [
        {
          id: "discussion.finding",
          label: "The main finding, restated",
          status: "present",
          question: "Does the Discussion open by restating the main finding?",
          plain: "The reader has just come through the Results. Open by saying, in one sentence, what they showed.",
          frame: "“In this study we found that [main finding].”",
          source: WORD_MOVE_SOURCE,
          evidence: "It is clearly proven that the the effect of vector control was large, and the the data agree.",
          note: "",
          learn_ref: null,
        },
        {
          id: "discussion.prior",
          label: "Against earlier work",
          status: "missing",
          question: "Does the Discussion compare the findings with earlier work?",
          plain: "A finding means more next to what was known before. Say whether it agrees, and if not, why.",
          frame: "“Our estimate is [consistent with / higher than] [earlier work], which [reason].”",
          source: WORD_MOVE_SOURCE,
          evidence: null,
          note: "",
          learn_ref: null,
        },
        {
          id: "discussion.limits",
          label: "What this cannot show",
          status: "missing",
          question: "Does the Discussion state the limitations?",
          plain: "A limitation stated by the author is a boundary; one found by the reviewer is a rebuttal. State them first.",
          frame: "“This study has limitations. First, [constraint], which means [bounded consequence].”",
          source: WORD_MOVE_SOURCE,
          evidence: null,
          note: "",
          learn_ref: null,
        },
        {
          id: "discussion.implication",
          label: "What should change",
          status: "missing",
          question: "Does the ending say what a reader could do with this?",
          plain: "The ending widens back out: say what should change in the field or in practice, and for whom.",
          frame: "“[Decision-makers] could use this to [action], provided [condition].”",
          source: WORD_MOVE_SOURCE,
          evidence: null,
          note: "",
          learn_ref: null,
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
      evidence: ["It is clearly proven that the the effect of vector control was large, and the the data agree."],
      message:
        "1 claim-type sentence in the Discussion but no warrant signal (because, this suggests that, consistent with). The reader is given the claim but not why the evidence supports it.",
      source: "M. Wallace & A. Wray (2016), Critical Reading and Writing for Postgraduates, 3rd ed., SAGE; S. Toulmin (1958), The Uses of Argument",
    },
  ],
  hedging: [
    { section: "methods", label: "Methods", words: 21, hedges_per_100w: 0, boosters_per_100w: 0, reading: "flat" },
    { section: "discussion", label: "Discussion", words: 17, hedges_per_100w: 0, boosters_per_100w: 5.88, reading: "assertive" },
  ],
};

/** The profile a check ran under; a guess names the headings it rested on (S4c). */
export function wordProfileFor(type: DocumentType | null | undefined): ProfileInfo {
  const p = profileFor(type);
  return { ...p, evidence: p.guessed ? "Methods" : "" };
}

/** A STROBE report for DOC (S4c). Synthetic: one item reported by the document's own sentence, two that need the writer's check. */
export const WORD_CHECKLIST: ChecklistReport = {
  id: "strobe",
  label: "STROBE",
  design: "observational studies (cohort, case-control, cross-sectional)",
  source: "STROBE Statement (2007), checklist for observational studies",
  suggested: false,
  reported: 1,
  total: 3,
  note: "1 of 3 items were found in the text. The others need your check: they may be reported in a table, a figure or the supplement, or not apply to this study. This checks reporting only, never the science.",
  items: [
    {
      id: "methods.statistics",
      topic: "Statistical methods",
      question: "Are the statistical methods described, including how confounding was handled?",
      plain: "A reader needs the model to judge the estimate.",
      sections: ["methods"],
      status: "reported",
      evidence: "In order to estimate the effective reproduction number, a renewal model was fitted.",
    },
    {
      id: "methods.setting",
      topic: "Setting",
      question: "Are the setting, locations and dates of the study described?",
      plain: "Where and when the data come from decides whom the result applies to.",
      sections: ["methods"],
      status: "needs_check",
      evidence: null,
    },
    {
      id: "discussion.limitations",
      topic: "Limitations",
      question: "Are the limitations discussed, with the direction of any bias?",
      plain: "Stating the limits yourself keeps the claim inside them.",
      sections: ["discussion"],
      status: "needs_check",
      evidence: null,
    },
  ],
};

export const reviseResponse = {
  schema_version: "1",
  signed_in: false,
  warnings: [],
  mode: "revise",
  hidden_by_mode: 0,
  profile: wordProfileFor("auto"),
  review: WORD_REVIEW,
  narrative: WORD_NARRATIVE,
  checklist: null,
  suggested_checklist: "strobe",
  suggestions: ALL,
  counts: { correction: 4, improvement: 2, convention: 2 },
  hidden_preferences: 1,
  metrics: null,
  sections_detected: ["methods", "discussion"],
  health: HEALTHY,
  engine: { service_version: "0.3.0", core_version: "0.9.0", rules_loaded: 90 },
  elapsed_ms: 321,
  coverage: {
    paragraphs: DOC.length,
    table_paragraphs: 1,
    not_checked: ["footnotes", "endnotes", "headers and footers", "text boxes", "comments"],
  },
} satisfies AnalyzeWordResponse;

/** Draft: document-level checks held back (the long-sentence and booster cards stay; these are sentence-level). */
export const draftResponse = {
  ...reviseResponse,
  mode: "draft",
  hidden_by_mode: 2,
  suggestions: SENTENCE_LEVEL,
  counts: { correction: 4, improvement: 2, convention: 1 },
  review: null,
  narrative: null,
} satisfies AnalyzeWordResponse;

/** The answer for a request, as the engine would give it: the stage, the profile asked for, the brief and the map only when asked. */
export function wordResponseFor(req: AnalyzeWordRequest): AnalyzeWordResponse {
  const base = req.options?.mode === "draft" ? draftResponse : reviseResponse;
  return {
    ...base,
    profile: wordProfileFor(req.options?.document_type),
    review: req.options?.review ? WORD_REVIEW : null,
    narrative: req.options?.narrative ? WORD_NARRATIVE : null,
    // "auto" and "strobe" both resolve to STROBE for DOC; another checklist comes back with its own label.
    checklist: req.options?.checklist
      ? req.options.checklist === "auto" || req.options.checklist === "strobe"
        ? WORD_CHECKLIST
        : { ...WORD_CHECKLIST, id: req.options.checklist, label: req.options.checklist.toUpperCase() }
      : null,
  };
}

export const healthResponse = (tiers: TierHealth[] = HEALTHY) =>
  ({
    status: tiers.some((t) => !t.ok && t.tier !== "gec") ? "degraded" : "ok",
    tiers,
    engine: reviseResponse.engine,
  }) satisfies HealthResponse;

/* ---------- page setup ---------- */

/** Serve the fake office.js in place of Microsoft's, configured for this test. */
export async function fakeOffice(page: Page, config: Partial<FakeWordConfig> = {}) {
  const full: FakeWordConfig = { paragraphs: DOC, ...config };
  await page.addInitScript((cfg) => {
    (window as unknown as { __fakeWordConfig: unknown }).__fakeWordConfig = cfg;
  }, full);
  await page.route(OFFICE_JS, (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: fakeOfficeScript() }),
  );
}

export function wordState(page: Page): Promise<FakeWordState> {
  return page.evaluate(() => (window as unknown as { __fakeWord: FakeWordState }).__fakeWord);
}

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, GET, OPTIONS",
  "access-control-allow-headers": "content-type, authorization",
  "access-control-expose-headers": "retry-after, x-request-id",
};

export interface WordCall {
  url: string;
  body: AnalyzeWordRequest;
  authorization: string | undefined;
}

/** Mock one engine's /v1/analyze-word, /v1/health and /v1/rules (`rules`: the registry; [] for one that lists nothing). */
export async function mockWordEngine(
  page: Page,
  base: string,
  opts: {
    respond?: (req: AnalyzeWordRequest, route: Route) => Promise<void> | void;
    health?: TierHealth[];
    rules?: RuleInfo[];
  } = {},
): Promise<WordCall[]> {
  const calls: WordCall[] = [];
  await page.route(`${base}/v1/**`, async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const path = new URL(req.url()).pathname;
    if (path === "/v1/health") {
      return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(healthResponse(opts.health)) });
    }
    if (path === "/v1/rules") {
      return route.fulfill({
        status: 200,
        headers: CORS,
        contentType: "application/json",
        body: JSON.stringify({ rules: opts.rules ?? WORD_RULES, profiles: PROFILES }),
      });
    }
    if (path !== "/v1/analyze-word") return route.fulfill({ status: 404, headers: CORS, body: "" });
    const body = req.postDataJSON() as AnalyzeWordRequest;
    calls.push({ url: req.url(), body, authorization: req.headers()["authorization"] });
    if (opts.respond) return opts.respond(body, route);
    return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(wordResponseFor(body)) });
  });
  return calls;
}

export function fulfillJson(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
}
