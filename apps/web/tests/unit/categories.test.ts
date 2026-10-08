import { describe, expect, it } from "vitest";
import { CATEGORIES, CATEGORY_ORDER, categoryMeta, countByCategory, sectionLabel, tierLabel } from "@/lib/categories";
import type { Category } from "@researchly/contract";
import { sugg } from "./helpers";

describe("category mapping", () => {
  it("covers exactly the four contract categories, in priority order", () => {
    const all: Category[] = ["correction", "improvement", "convention", "preference"];
    expect([...CATEGORY_ORDER]).toEqual(all);
    expect(Object.keys(CATEGORIES).sort()).toEqual([...all].sort());
  });

  it("gives every category a distinct label and a distinct underline style (colour is never the only cue)", () => {
    const labels = CATEGORY_ORDER.map((c) => CATEGORIES[c].label);
    const underlines = CATEGORY_ORDER.map((c) => CATEGORIES[c].underline);
    expect(new Set(labels).size).toBe(4);
    expect(new Set(underlines).size).toBe(4);
  });

  it("never words a convention as an error", () => {
    const blurb = CATEGORIES.convention.blurb.toLowerCase();
    expect(blurb).toContain("not an error");
    expect(CATEGORIES.convention.label).toBe("Convention");
  });

  it("falls back to improvement — never correction — for an unknown category", () => {
    expect(categoryMeta("mystery").id).toBe("improvement");
    expect(categoryMeta("convention").id).toBe("convention");
  });

  it("counts by category and ignores unknown categories", () => {
    const counts = countByCategory([
      sugg("a", 0, 1, "correction"),
      sugg("b", 0, 1, "correction"),
      sugg("c", 0, 1, "convention"),
      { category: "bogus" as Category },
    ]);
    expect(counts).toEqual({ correction: 2, improvement: 0, convention: 1, preference: 0 });
  });

  it("labels sections and hides unknown ones", () => {
    expect(sectionLabel("methods")).toBe("Methods");
    expect(sectionLabel("unknown")).toBeNull();
    expect(sectionLabel("")).toBeNull();
    expect(sectionLabel("acknowledgements")).toBe("Acknowledgements");
  });

  it("names the tier that produced a suggestion", () => {
    expect(tierLabel("grammar")).toMatch(/LanguageTool/);
    expect(tierLabel("gec")).toMatch(/non-generative/);
    expect(tierLabel("craft")).toBe("Writing-craft rule");
    expect(tierLabel("future")).toBe("future check");
  });
});
