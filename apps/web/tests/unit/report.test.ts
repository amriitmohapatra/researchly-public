import { describe, expect, it } from "vitest";
import type { TierHealth } from "@researchly/contract";
import { learnCard, LEARN_PATH } from "@/lib/learn";
import { recordCheck } from "@/lib/record-progress";
import {
  dismissedReportLine,
  modeLabel,
  readWarnings,
  STALE_REPORT_LINE,
  timesLine,
  unavailableLine,
  unavailableTiers,
} from "@/lib/report";
import { happyResponse, SAMPLE_LEARN_REFS } from "../../e2e/fixtures";

const tier = (t: string, label: string, ok: boolean): TierHealth => ({ tier: t, label, ok, state: ok ? "ready" : "error", detail: "", remedy: "" });

describe("the printed report's context (review R8)", () => {
  const checked = new Date(Date.UTC(2026, 9, 8, 9, 5));
  const printed = new Date(Date.UTC(2026, 9, 8, 11, 40));

  it("prints when the text was checked and when the page was printed", () => {
    const line = timesLine(checked, printed, "en-GB");
    expect(line).toMatch(/^Checked 8 October 2026.* · Printed 8 October 2026/);
    expect(timesLine(null, printed, "en-GB")).toMatch(/^Printed 8 October 2026/);
  });

  it("names the mode", () => {
    expect(modeLabel("revise")).toBe("Revise mode");
    expect(modeLabel("draft")).toBe("Draft mode");
    expect(modeLabel(undefined)).toBe("Revise mode");
  });

  it("names every tier that did not contribute, once, in the engine's order, the expected ones included", () => {
    const health = [tier("parser", "Parser", true), tier("grammar", "Grammar", false), tier("gec", "Learned corrections", false), tier("grammar", "Grammar", false)];
    expect(unavailableTiers(health)).toEqual(["Grammar", "Learned corrections"]);
    expect(unavailableLine(unavailableTiers(health))).toBe("Not available for this check: Grammar, Learned corrections.");
    expect(unavailableTiers([tier("files", "", false)])).toEqual(["files"]);
    expect(unavailableTiers(undefined)).toEqual([]);
    expect(unavailableLine([])).toBeNull();
  });

  it("lists what was skipped while reading, from the file and the response, once each", () => {
    expect(readWarnings(["A table was skipped.", "  "], ["A figure was skipped.", "A table was skipped."])).toEqual([
      "A figure was skipped.",
      "A table was skipped.",
    ]);
    expect(readWarnings(undefined, null)).toEqual([]);
  });

  it("says what was dismissed and that a changed editor is not what was checked", () => {
    expect(dismissedReportLine(0)).toBeNull();
    expect(dismissedReportLine(1)).toBe("1 suggestion dismissed on screen is left out of this report.");
    expect(dismissedReportLine(3)).toBe("3 suggestions dismissed on screen are left out of this report.");
    expect(STALE_REPORT_LINE).toBe("This report describes the version that was checked, not the text now in the editor.");
  });
});

describe("the Learn cards", () => {
  it("finds a card by the engine's learn_ref, and nothing for a blank or unknown one", () => {
    expect(learnCard("hedging")?.title).toBeTruthy();
    expect(learnCard(" hedging ")?.id).toBe("hedging");
    for (const v of [null, undefined, "", "  ", "no-such-card"]) expect(learnCard(v)).toBeNull();
    expect(LEARN_PATH).toBe("/learn");
  });

  it("every learn_ref the e2e fixtures use names a real card (they mirror the engine, where every suggestion has one)", () => {
    for (const [rule, ref] of Object.entries(SAMPLE_LEARN_REFS)) if (ref) expect(learnCard(ref), rule).not.toBeNull();
  });
});

describe("progress recording from the website", () => {
  const data = happyResponse;

  it("records only for a signed-in writer who keeps their progress, as counts", () => {
    const calls: unknown[] = [];
    const record = async (d: unknown, keep: boolean) => {
      calls.push([d, keep]);
      return { ok: true };
    };
    recordCheck(data, { signedIn: false, keep: true }, record);
    recordCheck(data, { signedIn: true, keep: false }, record);
    expect(calls).toHaveLength(0);
    recordCheck(data, { signedIn: true, keep: true }, record);
    expect(calls).toEqual([[data, true]]);
  });

  it("never lets a failure reach the check: a rejection or a throw is swallowed", async () => {
    expect(() => recordCheck(data, { signedIn: true, keep: true }, () => Promise.reject(new Error("offline")))).not.toThrow();
    expect(() =>
      recordCheck(data, { signedIn: true, keep: true }, () => {
        throw new Error("boom");
      }),
    ).not.toThrow();
    await new Promise((r) => setTimeout(r, 0)); // an unhandled rejection would fail the run here
  });
});
