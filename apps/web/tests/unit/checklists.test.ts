import { describe, expect, it } from "vitest";
import type { ChecklistChoiceInfo } from "@researchly/contract";
import {
  CHECKLIST_SCOPE_LINE,
  CHECKLIST_STATUS_WORD,
  checklistHelp,
  checklistOffer,
  checklistOption,
  FALLBACK_CHECKLISTS,
  isChecklistChoice,
  isChecklistSetting,
} from "@/lib/checklists";
import { registryChecklists } from "@/lib/registry";

describe("reporting checklists: the choices", () => {
  it("knows the contract's checklists, Auto and None, and nothing else", () => {
    for (const v of ["auto", "strobe", "consort", "prisma", "epiforge"]) {
      expect(isChecklistChoice(v), v).toBe(true);
      expect(isChecklistSetting(v), v).toBe(true);
    }
    expect(isChecklistSetting("none")).toBe(true);
    expect(isChecklistChoice("none")).toBe(false);
    for (const v of ["STROBE", "", null, undefined, 3, "tripod"]) expect(isChecklistSetting(v)).toBe(false);
  });

  it("sends nothing for None and the id otherwise", () => {
    expect(checklistOption("none")).toBeNull();
    expect(checklistOption("auto")).toBe("auto");
    expect(checklistOption("prisma")).toBe("prisma");
  });

  it("falls back to the engine's own list, in its order, when the registry has none", () => {
    expect(FALLBACK_CHECKLISTS.map((c) => c.id)).toEqual(["strobe", "consort", "prisma", "epiforge"]);
    expect(registryChecklists(null)).toBe(FALLBACK_CHECKLISTS);
    expect(registryChecklists({ rules: [], profiles: [], checklists: [] })).toBe(FALLBACK_CHECKLISTS);
    const own: ChecklistChoiceInfo[] = [{ id: "strobe", label: "STROBE (2007)", design: "cohort studies", pack: "Epi" }];
    expect(registryChecklists({ rules: [], profiles: [], checklists: own })).toBe(own);
  });

  it("says what the chosen checklist is for under the control, from the registry's design", () => {
    expect(checklistHelp(FALLBACK_CHECKLISTS, "none")).toBe("");
    expect(checklistHelp(FALLBACK_CHECKLISTS, "auto")).toMatch(/own words point to/);
    expect(checklistHelp(FALLBACK_CHECKLISTS, "consort")).toBe("For randomised controlled trials.");
    expect(checklistHelp([], "consort")).toBe("");
  });
});

describe("the checklist offer", () => {
  it("offers the checklist the text's words point to, with the registry's label", () => {
    expect(checklistOffer("epiforge", FALLBACK_CHECKLISTS)).toEqual({
      id: "epiforge",
      label: "EPIFORGE",
      sentence: "This reads like an epidemic forecast. Check it against EPIFORGE?",
    });
    expect(checklistOffer("strobe", FALLBACK_CHECKLISTS)?.sentence).toBe("This reads like an observational study. Check it against STROBE?");
    expect(checklistOffer("consort", FALLBACK_CHECKLISTS)?.sentence).toBe("This reads like a randomised controlled trial. Check it against CONSORT?");
    expect(checklistOffer("prisma", FALLBACK_CHECKLISTS)?.sentence).toBe(
      "This reads like a systematic review or meta-analysis. Check it against PRISMA?",
    );
    const relabelled: ChecklistChoiceInfo[] = [{ id: "prisma", label: "PRISMA 2020", design: "systematic reviews", pack: "Epi" }];
    expect(checklistOffer("prisma", relabelled)?.label).toBe("PRISMA 2020");
  });

  it("uses the built-in label when the registry has not arrived", () => {
    expect(checklistOffer("consort", [])?.label).toBe("CONSORT");
  });

  it("offers nothing without a suggestion, for Auto, or for an id this page cannot ask for", () => {
    expect(checklistOffer(null, FALLBACK_CHECKLISTS)).toBeNull();
    expect(checklistOffer(undefined, FALLBACK_CHECKLISTS)).toBeNull();
    expect(checklistOffer("", FALLBACK_CHECKLISTS)).toBeNull();
    expect(checklistOffer("auto", FALLBACK_CHECKLISTS)).toBeNull();
    expect(checklistOffer("tripod", [{ id: "tripod", label: "TRIPOD", design: "prediction models", pack: "Epi" }])).toBeNull();
  });
});

describe("the checklist's words", () => {
  it("says every status in words, never as a verdict on the science", () => {
    expect(CHECKLIST_STATUS_WORD).toEqual({ reported: "reported", needs_check: "needs your check" });
    expect(CHECKLIST_SCOPE_LINE).toBe("This checks reporting only, never the science.");
  });
});
