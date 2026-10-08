/**
 * API contract v1 for Researchly surfaces (web app, Word add-in).
 *
 * Generated types live in ./schema.d.ts (from ../openapi.json, which the
 * engine service exports from its Pydantic models). These aliases are the
 * only hand-written part: names, not shapes.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type AnalyzeRequest = S["AnalyzeRequest"];
export type AnalyzeOptions = S["AnalyzeOptions"];
export type AnalyzeResponse = S["AnalyzeResponse"];
export type Suggestion = S["Suggestion"];
export type Span = S["Span"];
export type Category = S["Category"];
export type Format = S["Format"];
export type FixSafety = S["FixSafety"];
export type Metrics = S["Metrics"];
export type TierHealth = S["TierHealth"];
export type EngineInfo = S["EngineInfo"];
export type HealthResponse = S["HealthResponse"];
export type RuleInfo = S["RuleInfo"];
export type RulesResponse = S["RulesResponse"];
export type ErrorResponse = S["ErrorResponse"];
export type AnalyzeFileResponse = S["AnalyzeFileResponse"];
export type SourceInfo = S["SourceInfo"];
export type SourceFormat = S["SourceFormat"];
export type Segment = S["Segment"];
export type StructureItem = S["StructureItem"];
export type Mode = S["Mode"];
export type Scope = S["Scope"];
export type WordParagraph = S["WordParagraph"];
export type AnalyzeWordRequest = S["AnalyzeWordRequest"];
export type AnalyzeWordResponse = S["AnalyzeWordResponse"];
export type WordSuggestion = S["WordSuggestion"];
export type WordLocation = S["WordLocation"];
export type Coverage = S["Coverage"];
export type DocumentType = S["DocumentType"];
export type ProfileInfo = S["ProfileInfo"];
export type ProfileChoice = S["ProfileChoice"];
export type ReviewReport = S["ReviewReport"];
export type ReviewQuestion = S["ReviewQuestion"];
export type ReviewRuleCount = S["ReviewRuleCount"];
export type NarrativeMap = S["NarrativeMap"];
export type NarrativeSection = S["NarrativeSection"];
export type NarrativeMove = S["NarrativeMove"];
export type MoveStatus = S["MoveStatus"];
export type MissingLink = S["MissingLink"];
export type HedgingPoint = S["HedgingPoint"];
export type ChecklistChoice = S["ChecklistChoice"];
export type ChecklistReport = S["ChecklistReport"];
export type ChecklistItem = S["ChecklistItem"];
export type ChecklistChoiceInfo = S["ChecklistChoiceInfo"];
export type LearnCard = S["LearnCard"];
export type LearnResponse = S["LearnResponse"];

/** Mirrors schemas.MAX_CONTENT_CHARS; checked client-side for usability only. */
export const MAX_CONTENT_CHARS = 1_000_000;

/** Mirrors schemas.MAX_WORD_PARAGRAPHS (/v1/analyze-word). */
export const MAX_WORD_PARAGRAPHS = 50_000;

/** Article types a caller can check as (S4), in the engine's display order; `GET /v1/rules` carries their labels. */
export const DOCUMENT_TYPES = [
  "auto",
  "general",
  "manuscript",
  "thesis-chapter",
  "abstract",
  "commentary",
  "policy-brief",
  "grant",
  "response-to-reviewers",
] as const satisfies readonly DocumentType[];

/**
 * The engine's default upload cap for /v1/analyze-file (RESEARCHLY_MAX_UPLOAD_BYTES,
 * 25 MiB; docs/s2-design.md §4). Checked client-side for usability only.
 */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

/** File types /v1/analyze-file reads (docs/s2-design.md §4), lower-case. */
export const UPLOAD_EXTENSIONS = [".docx", ".tex", ".zip", ".md", ".qmd", ".rmd", ".txt"] as const;

import readingKey from "../reading-key.json";

/** One reading-key specimen: before + flagged + after is a sentence the engine flags. */
export type Specimen = { before: string; flagged: string; after: string; note: string };

/**
 * The reading key's specimens, one per category. Shared with the engine's test
 * suite (packages/core/tests/test_reading_key.py), which runs each through
 * api.analyze and checks the category, so the key cannot drift from the engine.
 */
export const READING_KEY: Record<Category, Specimen> = {
  correction: readingKey.correction,
  improvement: readingKey.improvement,
  convention: readingKey.convention,
  preference: readingKey.preference,
};

import learnJson from "../learn.json";

/** Every Learn card (S4), grouped in reading order; generated from packages/core/researchly/learn.py and checked by its tests. */
export const LEARN_CARDS: readonly LearnCard[] = (learnJson as { cards: LearnCard[] }).cards;
