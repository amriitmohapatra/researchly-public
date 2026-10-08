import { describe, expect, it } from "vitest";
import type { ProgressEvent } from "@/lib/progress";
import { formatRate, MIN_FIRES, ratePer1000, ruleTrends, sparkPoints, trendWord } from "@/lib/progress-view";

const ev = (day: number, words: number, counts: Record<string, number>): ProgressEvent => ({
  created_at: `2026-10-0${day}T10:00:00Z`,
  words,
  document_type: "manuscript",
  counts,
});

describe("progress: each rule's rate per 1,000 words over the recorded checks (S4c)", () => {
  it("orders checks oldest first (loadProgress returns newest first) and keeps rules that fired at least twice", () => {
    const events = [
      ev(3, 2000, { G106: 2 }),
      ev(2, 1000, { G106: 3, W202: 1 }),
      ev(1, 500, { G106: 4, C201: 1 }),
    ];
    const { checks, trends } = ruleTrends(events);
    expect(checks).toBe(3);
    expect(MIN_FIRES).toBe(2);
    // W202 and C201 fired once each: not shown.
    expect(trends.map((t) => t.ruleId)).toEqual(["G106"]);
    expect(trends[0]).toEqual({ ruleId: "G106", rates: [8, 3, 1], first: 8, latest: 1, word: "fewer" });
  });

  it("a rule absent from a check counts as zero there, and skips checks of no words", () => {
    const { checks, trends } = ruleTrends([ev(1, 1000, { S001: 2 }), ev(2, 0, { S001: 9 }), ev(3, 1000, {})]);
    expect(checks).toBe(2);
    expect(trends[0]!.rates).toEqual([2, 0]);
  });

  it("one check: a value but no direction yet", () => {
    const { trends } = ruleTrends([ev(1, 1000, { G106: 3 })]);
    expect(trends[0]!.word).toBeNull();
  });

  it("says fewer, about the same or more, ignoring small differences", () => {
    expect(trendWord(4, 1)).toBe("fewer");
    expect(trendWord(1, 4)).toBe("more");
    expect(trendWord(2, 2.3)).toBe("about the same");
    expect(trendWord(0, 0.4)).toBe("about the same");
    expect(trendWord(10, 8.5)).toBe("about the same");
    expect(trendWord(10, 7.5)).toBe("fewer");
  });

  it("rates and their wording", () => {
    expect(ratePer1000(3, 1000)).toBe(3);
    expect(ratePer1000(1, 3000)).toBe(0.3);
    expect(ratePer1000(1, 0)).toBe(0);
    expect(formatRate(3)).toBe("3");
    expect(formatRate(0.34)).toBe("0.3");
    expect(formatRate(12.25)).toBe("12.3");
  });

  it("the sparkline runs from zero at the bottom to its own highest value at the top", () => {
    const pts = sparkPoints([0, 5, 10], 100, 40, 4);
    expect(pts.map((p) => p.x)).toEqual([4, 50, 96]);
    expect(pts.map((p) => p.y)).toEqual([36, 20, 4]);
    expect(sparkPoints([2], 100, 40)).toEqual([{ x: 50, y: 4 }]);
    expect(sparkPoints([0, 0], 100, 40, 4).map((p) => p.y)).toEqual([36, 36]);
  });
});
