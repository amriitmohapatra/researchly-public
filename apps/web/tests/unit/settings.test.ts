import { describe, expect, it } from "vitest";
import { accountErrorMessage } from "@/lib/account";
import {
  dictionaryCandidate,
  isRuleId,
  MAX_DICTIONARY_WORDS,
  normaliseSettings,
  validateWord,
} from "@/lib/settings";

describe("dictionary limits (as the database enforces them)", () => {
  it("accepts one word up to 64 characters", () => {
    expect(validateWord("nowcasting")).toBeNull();
    expect(validateWord("  Rt  ")).toBeNull();
    expect(validateWord("x".repeat(64))).toBeNull();
    expect(validateWord("𝑅".repeat(64))).toBeNull(); // counted in characters, not UTF-16 units
  });
  it("refuses empty, spaced and over-long words", () => {
    expect(validateWord("   ")?.kind).toBe("empty");
    expect(validateWord("serial interval")?.kind).toBe("spaces");
    expect(validateWord("tab\tword")?.kind).toBe("spaces");
    expect(validateWord("x".repeat(65))?.kind).toBe("too_long");
  });
  it("refuses duplicates and a full dictionary", () => {
    expect(validateWord("Rt", ["Rt"])?.kind).toBe("duplicate");
    const full = Array.from({ length: MAX_DICTIONARY_WORDS }, (_, i) => `w${i}`);
    expect(validateWord("new", full)?.kind).toBe("full");
    expect(validateWord("new", full)?.message).toContain("5,000");
  });
  it("offers 'Add to dictionary' only for a single valid word", () => {
    expect(dictionaryCandidate("nowcasting")).toBe("nowcasting");
    expect(dictionaryCandidate("the the")).toBeNull();
    expect(dictionaryCandidate("")).toBeNull();
  });
});

describe("settings rows", () => {
  it("a missing row means defaults", () => {
    // The table's defaults (locale en-US), so the page and the engine agree.
    expect(normaliseSettings(null)).toEqual({ disabled_rules: [], show_preferences: false, locale: "en-US" });
  });
  it("drops values the table would not hold", () => {
    expect(
      normaliseSettings({ disabled_rules: ["G101", "bad id", "G101", 7], show_preferences: "yes", locale: "fr-FR" }),
    ).toEqual({ disabled_rules: ["G101"], show_preferences: false, locale: "en-US" });
    expect(normaliseSettings({ disabled_rules: ["C120"], show_preferences: true, locale: "en-GB" })).toEqual({
      disabled_rules: ["C120"],
      show_preferences: true,
      locale: "en-GB",
    });
  });
  it("rule ids match the table's check", () => {
    expect(isRuleId("G101")).toBe(true);
    expect(isRuleId("LT001")).toBe(true);
    expect(isRuleId("g101")).toBe(false);
    expect(isRuleId("MORFOLOGIK_RULE_EN")).toBe(false);
  });
});

describe("account error messages", () => {
  it("explain constraint and limit failures without Postgres's own words", () => {
    expect(accountErrorMessage({ code: "23514", message: 'new row violates check constraint "dictionary_words_word_shape"' })).toContain(
      "64 characters",
    );
    // The cap trigger raises check_violation too (supabase/migrations, researchly_dictionary_cap).
    expect(accountErrorMessage({ code: "23514", message: "dictionary is full (5000 words)" })).toContain("5,000");
    expect(accountErrorMessage({ code: "PGRST301", message: "JWT expired" })).toContain("Sign in again");
    expect(accountErrorMessage({ message: "TypeError: Failed to fetch" })).toContain("connection");
    expect(accountErrorMessage({ code: "XX000", message: "internal detail" })).not.toContain("internal detail");
  });
});
