/**
 * Engine responses for the accounts (S2) e2e specs. All text is synthetic,
 * written for these tests. Offsets are computed here; the text is ASCII, so
 * code points and UTF-16 units coincide.
 */
import type { AnalyzeFileResponse, AnalyzeResponse, ErrorResponse, RuleInfo, Segment, Suggestion } from "@researchly/contract";
import { happyResponse } from "./fixtures";

function at(text: string, needle: string, from = 0): [number, number] {
  const i = text.indexOf(needle, from);
  if (i < 0) throw new Error(`fixture needle not found: ${needle}`);
  return [i, i + needle.length];
}

function line(text: string, offset: number): number {
  return text.slice(0, offset).split("\n").length;
}

function sugg(text: string, needle: string, extra: Partial<Suggestion> & Pick<Suggestion, "id" | "rule_id">, from = 0): Suggestion {
  const [start, end] = at(text, needle, from);
  return {
    rule_name: "Test rule",
    category: "improvement",
    tier: "craft",
    span: { start, end, line: line(text, start), col: start - text.lastIndexOf("\n", start - 1) },
    section: "unknown",
    message: "A synthetic message.",
    why: "A synthetic explanation.",
    plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    source: "The Craft of Scientific Writing §4",
    learn_ref: null,
    replacement: null,
    fix_safety: "review",
    confidence: 1,
    text: needle,
    ...extra,
  };
}

/* ---------- pasted text, signed in ---------- */

export const PASTE_TEXT =
  "Methods\nWe fitted a nowcasting model to daily counts. In order to estimate the delay, a gamma distribution was used.\n";

export const nowcastingSpelling = sugg(PASTE_TEXT, "nowcasting", {
  id: "e2e-spell-1",
  rule_id: "S001",
  rule_name: "Unknown word",
  category: "correction",
  tier: "spelling",
  section: "methods",
  message: "‘nowcasting’ is not in the dictionary.",
  why: "Possible misspelling. If it is a term from your field, add it to your dictionary.",
  plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
  source: "Spelling tier: SymSpell with a scientific lexicon",
});

export const wordyPhrase = sugg(PASTE_TEXT, "In order to", {
  id: "e2e-wordy-1",
  rule_id: "C120",
  rule_name: "Wordy phrase",
  section: "methods",
  message: "‘In order to’ can usually be ‘To’.",
  replacement: "To",
});

export const signedInPaste = {
  ...happyResponse,
  signed_in: true,
  suggestions: [nowcastingSpelling, wordyPhrase],
  counts: { correction: 1, improvement: 1 },
  hidden_preferences: 0,
} satisfies AnalyzeResponse;

/** After muting C120 the engine no longer returns it. */
export const afterMute = {
  ...signedInPaste,
  suggestions: [nowcastingSpelling],
  counts: { correction: 1 },
} satisfies AnalyzeResponse;

/** After adding "nowcasting" to the dictionary. */
export const afterAddWord = {
  ...signedInPaste,
  suggestions: [wordyPhrase],
  counts: { improvement: 1 },
} satisfies AnalyzeResponse;

/* ---------- files ---------- */

export const MD_TEXT = "# Discussion\n\nThese results clearly prove that the intervention works.\n";

export const mdResponse = {
  ...happyResponse,
  signed_in: true,
  suggestions: [
    sugg(MD_TEXT, "clearly prove", {
      id: "e2e-md-1",
      rule_id: "C201",
      rule_name: "Booster overclaims certainty",
      section: "discussion",
      message: "‘clearly prove’ claims more certainty than the evidence can carry.",
    }),
  ],
  counts: { improvement: 1 },
  hidden_preferences: 0,
  document: {
    filename: "chapter-5.md",
    format: "markdown",
    text: MD_TEXT,
    segments: [{ path: "chapter-5.md", start: 0, end: MD_TEXT.length, source_start: 0 }],
    structure: [],
    warnings: [],
  },
} satisfies AnalyzeFileResponse;

const MAIN = "\\section{Introduction}\nWe model dengue transmission.\nIt is clearly proven that control works.\n";
const METHODS = "\\section{Methods}\nCounts were aggregated weekly.\nThe the model was fitted in Stan.\n";
export const ZIP_TEXT = MAIN + METHODS;

const zipSegments: Segment[] = [
  { path: "main.tex", start: 0, end: MAIN.length, source_start: 0 },
  { path: "sections/methods.tex", start: MAIN.length, end: ZIP_TEXT.length, source_start: 0 },
];

export const zipResponse = {
  ...happyResponse,
  signed_in: true,
  suggestions: [
    sugg(ZIP_TEXT, "clearly proven", {
      id: "e2e-zip-1",
      rule_id: "C201",
      rule_name: "Booster overclaims certainty",
      section: "introduction",
      message: "‘clearly proven’ claims more certainty than the evidence can carry.",
    }),
    sugg(ZIP_TEXT, "The the", {
      id: "e2e-zip-2",
      rule_id: "S010",
      rule_name: "Repeated word",
      category: "correction",
      tier: "spelling",
      section: "methods",
      message: "‘the’ is repeated.",
    }),
  ],
  counts: { correction: 1, improvement: 1 },
  hidden_preferences: 0,
  sections_detected: ["introduction", "methods"],
  document: {
    filename: "thesis-chapter.zip",
    format: "latex",
    text: ZIP_TEXT,
    segments: zipSegments,
    structure: [],
    warnings: ["\\input{appendix} not found in the zip; skipped"],
  },
} satisfies AnalyzeFileResponse;

/* ---------- errors ---------- */

export const unauthorized = {
  error: { code: "unauthorized", message: "Your sign-in has expired or is not valid. Sign in again; your text is still here.", request_id: "req-401-a" },
} satisfies ErrorResponse;

export const signInRequired = {
  error: {
    code: "sign_in_required",
    message: "Without an account Researchly checks up to 1,500 words at a time. Sign in to check a whole chapter.",
    request_id: "req-401-b",
  },
} satisfies ErrorResponse;

export const authUnavailable = {
  error: { code: "auth_unavailable", message: "Sign-in could not be checked.", request_id: "req-503-c" },
} satisfies ErrorResponse;

/* ---------- rules (settings page) ---------- */

export const RULES: RuleInfo[] = [
  {
    id: "C120",
    name: "Wordy phrase",
    short: "Prefer the shorter phrase when it says the same.",
    why: "w",
    plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    source: "s",
    category: "improvement",
    tier: "craft",
    fix_safety: "safe",
    scope: "sentence",
  },
  {
    id: "G101",
    name: "Subject-verb agreement",
    short: "A verb should agree with its subject in number.",
    why: "w",
    plain: "In everyday words: the same advice, written for a reader who knows their science but not the grammar terms.",
    source: "s",
    category: "correction",
    tier: "grammar",
    fix_safety: "review",
    scope: "sentence",
  },
];
