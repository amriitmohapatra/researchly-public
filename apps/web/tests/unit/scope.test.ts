import { describe, expect, it } from "vitest";
import type { RuleInfo } from "@researchly/contract";
import { isDocumentWide, scopeMap, splitForSection } from "@/lib/scope";

const rule = (id: string, scope: RuleInfo["scope"]): RuleInfo => ({
  id,
  name: id,
  short: "s",
  why: "w",
  plain: "p",
  source: "src",
  category: "convention",
  tier: "craft",
  fix_safety: "review",
  scope,
});

describe("rule scope", () => {
  it("without the registry, the engine's document-wide rules are known by id", () => {
    for (const id of ["X101", "X202", "X501", "F601", "F612", "F613", "N101", "W211", "D902", "AB802"]) {
      expect(isDocumentWide(id, null), id).toBe(true);
    }
    for (const id of ["C120", "S010", "G106", "P110", "XY"]) expect(isDocumentWide(id, null), id).toBe(false);
  });

  it("the registry wins where it lists the rule; unlisted rules fall back", () => {
    const known = scopeMap([rule("C999", "document"), rule("X101", "sentence"), rule("C120", "sentence")]);
    expect(isDocumentWide("C999", known)).toBe(true);
    expect(isDocumentWide("X101", known)).toBe(false);
    expect(isDocumentWide("C120", known)).toBe(false);
    expect(isDocumentWide("F612", known)).toBe(true); // not listed: built-in list
  });

  it("splits a list into the section, the whole-document group and the rest", () => {
    const list = [
      { id: "a", rule_id: "C120", section: "methods" },
      { id: "b", rule_id: "F612", section: "methods" },
      { id: "c", rule_id: "C120", section: "discussion" },
      { id: "d", rule_id: "X101", section: "discussion" },
    ];
    const r = splitForSection(list, (s) => s.section === "methods", null);
    expect(r.inSection.map((s) => s.id)).toEqual(["a"]);
    expect(r.wholeDocument.map((s) => s.id)).toEqual(["b", "d"]);
    expect(r.elsewhere).toBe(1);
  });
});
