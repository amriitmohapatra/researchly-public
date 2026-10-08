/**
 * Account settings as this app sees them, and the limits the database
 * enforces (docs/s2-design.md §2). Pure and unit-tested; the reads and
 * writes are in lib/account.ts. Checking here is for usability only: the
 * table constraints and Row-Level Security are the real guard.
 */
export type Locale = "en-GB" | "en-US";

export interface UserSettings {
  disabled_rules: string[];
  show_preferences: boolean;
  locale: Locale;
}

/** A missing settings row means these (no row is created at sign-up); they match the table defaults. */
export const DEFAULT_SETTINGS: Readonly<UserSettings> = {
  disabled_rules: [],
  show_preferences: false,
  locale: "en-US",
};

export const LOCALES: readonly { value: Locale; label: string; example: string }[] = [
  { value: "en-US", label: "American English", example: "analyze, color, modeling" },
  { value: "en-GB", label: "British English", example: "analyse, colour, modelling" },
];

export const MAX_WORD_CHARS = 64;
export const MAX_DICTIONARY_WORDS = 5000;
export const MAX_MUTED_RULES = 200;
const RULE_ID = /^[A-Z]{1,4}[0-9]{1,4}$/;

export function isLocale(v: unknown): v is Locale {
  return v === "en-GB" || v === "en-US";
}

export function isRuleId(v: unknown): v is string {
  return typeof v === "string" && RULE_ID.test(v);
}

/** A settings row from the database, made safe to render (unknown values fall back to defaults). */
export function normaliseSettings(row: unknown): UserSettings {
  if (typeof row !== "object" || row === null) return { ...DEFAULT_SETTINGS, disabled_rules: [] };
  const r = row as Record<string, unknown>;
  const rules = Array.isArray(r.disabled_rules) ? r.disabled_rules.filter(isRuleId) : [];
  return {
    disabled_rules: [...new Set(rules)],
    show_preferences: r.show_preferences === true,
    locale: isLocale(r.locale) ? r.locale : DEFAULT_SETTINGS.locale,
  };
}

export type WordProblem = { kind: "empty" | "too_long" | "spaces" | "full" | "duplicate"; message: string };

const nf = new Intl.NumberFormat("en-GB");

/** The dictionary's limits, as the database enforces them: 1–64 characters, no whitespace, ≤ 5,000 words. */
export function validateWord(raw: string, existing: readonly string[] = []): WordProblem | null {
  const word = raw.trim();
  if (!word) return { kind: "empty", message: "Type a word to add." };
  if (/\s/.test(word)) return { kind: "spaces", message: "Add one word at a time, with no spaces." };
  if (Array.from(word).length > MAX_WORD_CHARS) {
    return { kind: "too_long", message: `Words can be up to ${MAX_WORD_CHARS} characters long.` };
  }
  if (existing.includes(word)) return { kind: "duplicate", message: `“${word}” is already in your dictionary.` };
  if (existing.length >= MAX_DICTIONARY_WORDS) {
    return {
      kind: "full",
      message: `Your dictionary is full (${nf.format(MAX_DICTIONARY_WORDS)} words). Remove a word to add another.`,
    };
  }
  return null;
}

/** Whether a flagged spelling can go straight into the dictionary (the card's "Add to dictionary"). */
export function dictionaryCandidate(text: string): string | null {
  const word = text.trim();
  return validateWord(word) === null ? word : null;
}
