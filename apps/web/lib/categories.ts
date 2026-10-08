/**
 * The four-type taxonomy (CLAUDE.md #3) as the UI presents it.
 *
 * Colour is never the only signal: every category also has a text label,
 * an icon shape and a distinct underline style. Conventions are advisory —
 * never red, never worded as an error. Preferences are hidden by default.
 */
import type { Category } from "@researchly/contract";

/** Display and highlight priority: when spans overlap, the earlier one styles the text. */
export const CATEGORY_ORDER: readonly Category[] = [
  "correction",
  "improvement",
  "convention",
  "preference",
];

export interface CategoryMeta {
  id: Category;
  /** Singular label shown on every badge. */
  label: string;
  plural: string;
  /** One line telling the writer how to read this kind of suggestion. */
  blurb: string;
  /** Underline style in the document view (non-colour cue). */
  underline: "solid" | "double" | "dotted" | "dashed";
}

export const CATEGORIES: Readonly<Record<Category, CategoryMeta>> = {
  correction: {
    id: "correction",
    label: "Correction",
    plural: "Corrections",
    blurb: "Likely an error: spelling, grammar or a factual slip in form.",
    underline: "solid",
  },
  improvement: {
    id: "improvement",
    label: "Improvement",
    plural: "Improvements",
    blurb: "Correct as written, but a reader would follow it more easily if revised.",
    underline: "double",
  },
  convention: {
    id: "convention",
    label: "Convention",
    plural: "Conventions",
    blurb: "Not an error: a convention of research writing you may choose to follow.",
    underline: "dotted",
  },
  preference: {
    id: "preference",
    label: "Preference",
    plural: "Preferences",
    blurb: "A matter of taste. Hidden unless you ask for it.",
    underline: "dashed",
  },
};

const KNOWN = new Set<string>(CATEGORY_ORDER);

/** Defensive: an unknown category from a newer engine is shown as an improvement, never as a correction. */
export function categoryMeta(c: string): CategoryMeta {
  return KNOWN.has(c) ? CATEGORIES[c as Category] : CATEGORIES.improvement;
}

export function countByCategory(items: readonly { category: Category }[]): Record<Category, number> {
  const out: Record<Category, number> = { correction: 0, improvement: 0, convention: 0, preference: 0 };
  for (const it of items) if (KNOWN.has(it.category)) out[it.category]++;
  return out;
}

/** Human label for the tier that produced a suggestion (provenance, CLAUDE.md #6). */
export function tierLabel(tier: string): string {
  switch (tier) {
    case "spelling":
      return "Spelling checker";
    case "grammar":
      return "Grammar checker (LanguageTool)";
    case "gec":
      return "Learned edit tagger (non-generative)";
    case "craft":
      return "Writing-craft rule";
    case "lens":
      return "Structure lens";
    case "discourse":
      return "Discourse check";
    case "critic":
      return "Learned critic";
    default:
      return tier ? `${tier} check` : "Check";
  }
}

const SECTION_NAMES: Record<string, string> = {
  abstract: "Abstract",
  introduction: "Introduction",
  methods: "Methods",
  results: "Results",
  limitations: "Limitations",
  discussion: "Discussion",
  conclusion: "Conclusion",
  appendix: "Appendix",
};

export function sectionLabel(section: string): string | null {
  if (!section || section === "unknown" || section === "body") return null;
  return SECTION_NAMES[section] ?? section.charAt(0).toUpperCase() + section.slice(1);
}
