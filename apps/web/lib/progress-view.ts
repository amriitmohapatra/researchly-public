/**
 * The progress page's view model (S4c): per rule, how often it fired per
 * 1,000 words in each recorded check, oldest first. Pure and unit-tested.
 * A trajectory to notice, never a score: no totals, no grade, no ranking
 * of the writer, only each rule's own line and a word for its direction.
 */
import type { ProgressEvent } from "./progress";

export type TrendWord = "fewer" | "about the same" | "more";

export interface RuleTrend {
  ruleId: string;
  /** Flags per 1,000 words in each recorded check, oldest first (0 where the rule did not fire). */
  rates: number[];
  first: number;
  latest: number;
  /** null with a single check: there is no direction yet. */
  word: TrendWord | null;
}

/** Rules shown: those that fired at least this many times across the recorded checks. */
export const MIN_FIRES = 2;

/** Flags per 1,000 words, to one decimal place. */
export function ratePer1000(count: number, words: number): number {
  if (!(words > 0) || !(count > 0)) return 0;
  return Math.round((count / words) * 10_000) / 10;
}

/**
 * The direction from the first check to the latest. Small differences are
 * "about the same": half a flag per 1,000 words, or a fifth of the larger
 * value, whichever is bigger, so a short check's noise is not read as change.
 */
export function trendWord(first: number, latest: number): TrendWord {
  const band = Math.max(0.5, 0.2 * Math.max(first, latest));
  if (Math.abs(latest - first) < band) return "about the same";
  return latest < first ? "fewer" : "more";
}

/** "3.2", "0", "12": a rate as written on the page. */
export function formatRate(r: number): string {
  return r.toLocaleString("en-GB", { maximumFractionDigits: 1 });
}

/**
 * Every rule that fired at least MIN_FIRES times, with its rate in each
 * check (oldest first). `events` may come newest first, as loadProgress
 * returns them; checks of no words are skipped (nothing to divide by).
 */
export function ruleTrends(events: readonly ProgressEvent[]): { checks: number; trends: RuleTrend[] } {
  const ordered = [...events]
    .filter((e) => e.words > 0)
    .sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0));
  const fires = new Map<string, number>();
  for (const e of ordered) {
    for (const [id, n] of Object.entries(e.counts ?? {})) {
      if (typeof n === "number" && n > 0) fires.set(id, (fires.get(id) ?? 0) + n);
    }
  }
  const trends = [...fires.entries()]
    .filter(([, n]) => n >= MIN_FIRES)
    .sort(([a, x], [b, y]) => y - x || (a < b ? -1 : 1))
    .map(([ruleId]): RuleTrend => {
      const rates = ordered.map((e) => ratePer1000(e.counts?.[ruleId] ?? 0, e.words));
      const first = rates[0] ?? 0;
      const latest = rates[rates.length - 1] ?? 0;
      return { ruleId, rates, first, latest, word: rates.length > 1 ? trendWord(first, latest) : null };
    });
  return { checks: ordered.length, trends };
}

/** The sparkline's points in a w × h box: x by check order, y from zero (bottom) to the line's own highest value. */
export function sparkPoints(rates: readonly number[], w: number, h: number, pad = 4): { x: number; y: number }[] {
  const max = Math.max(...rates, 0);
  const n = rates.length;
  return rates.map((r, i) => ({
    x: n === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (n - 1),
    y: max === 0 ? h - pad : h - pad - (r / max) * (h - 2 * pad),
  }));
}
