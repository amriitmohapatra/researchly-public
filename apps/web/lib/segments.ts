/**
 * Offsets and highlight segmentation.
 *
 * The engine is Python: its span offsets are `str` indices, i.e. Unicode
 * code points. JavaScript strings are indexed in UTF-16 code units, so any
 * character outside the Basic Multilingual Plane (emoji, mathematical
 * alphanumerics such as 𝑅, many CJK extensions) counts as 1 in the engine
 * and 2 here. Every offset is converted before it touches the string.
 *
 * Everything in this file is pure and unit-tested (tests/unit/segments.test.ts).
 */
import type { Category, Suggestion } from "@researchly/contract";
import { CATEGORY_ORDER } from "./categories";

/**
 * Maps code-point offsets to UTF-16 offsets for one string.
 * `toUtf16(i)` is defined for 0 ≤ i ≤ length (inclusive end); values outside
 * that range are clamped.
 */
export interface OffsetMap {
  /** Number of code points in the string (what Python's len() returns). */
  readonly length: number;
  toUtf16(codePointIndex: number): number;
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}
function isLowSurrogate(code: number): boolean {
  return code >= 0xdc00 && code <= 0xdfff;
}

/** Python-compatible length: counts code points, not UTF-16 units. */
export function codePointLength(text: string): number {
  let n = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (isHighSurrogate(c) && i + 1 < text.length && isLowSurrogate(text.charCodeAt(i + 1))) {
      i++;
    }
    n++;
  }
  return n;
}

export function buildOffsetMap(text: string): OffsetMap {
  // Fast path: no surrogate pairs at all → offsets are identical.
  if (!/[\uD800-\uDBFF][\uDC00-\uDFFF]/.test(text)) {
    const length = text.length;
    return {
      length,
      toUtf16: (i) => clamp(Math.trunc(i), 0, length),
    };
  }
  const cpLength = codePointLength(text);
  const table = new Uint32Array(cpLength + 1);
  let cp = 0;
  for (let i = 0; i < text.length; i++) {
    table[cp++] = i;
    const c = text.charCodeAt(i);
    if (isHighSurrogate(c) && i + 1 < text.length && isLowSurrogate(text.charCodeAt(i + 1))) {
      i++;
    }
  }
  table[cpLength] = text.length;
  return {
    length: cpLength,
    toUtf16: (i) => table[clamp(Math.trunc(i), 0, cpLength)] ?? text.length,
  };
}

function clamp(n: number, lo: number, hi: number): number {
  if (Number.isNaN(n)) return lo;
  return n < lo ? lo : n > hi ? hi : n;
}

/** A suggestion's span resolved to UTF-16 offsets into the submitted text. */
export interface ResolvedSpan {
  id: string;
  category: Category;
  start: number;
  end: number;
  /** False when the engine's span fell (partly) outside the text and was clamped. */
  inRange: boolean;
}

/**
 * Resolve every suggestion's span against `text`.
 *
 * Code points are the contract. As a guard against an engine that ever sends
 * UTF-16 offsets instead, a span whose code-point slice does not match
 * `suggestion.text` but whose raw UTF-16 slice does is taken at face value.
 * Spans that cannot be placed at all (start beyond the end of the text) are
 * dropped from the highlights; their cards still render.
 */
export function resolveSpans(text: string, suggestions: readonly Suggestion[]): ResolvedSpan[] {
  const map = buildOffsetMap(text);
  const out: ResolvedSpan[] = [];
  for (const s of suggestions) {
    let rawStart = Number(s.span.start);
    let rawEnd = Number(s.span.end);
    if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) continue;
    if (rawEnd < rawStart) [rawStart, rawEnd] = [rawEnd, rawStart];
    // Guard: an engine that sent UTF-16 offsets. Only trusted when the
    // code-point reading does not match the flagged text but the raw one does.
    if (
      s.text &&
      rawStart >= 0 &&
      rawEnd <= text.length &&
      text.slice(rawStart, rawEnd) === s.text &&
      !(rawEnd <= map.length && text.slice(map.toUtf16(rawStart), map.toUtf16(rawEnd)) === s.text)
    ) {
      out.push({ id: s.id, category: s.category, start: rawStart, end: rawEnd, inRange: true });
      continue;
    }
    if (rawStart > map.length || rawEnd < 0) continue; // nothing to anchor to
    const inRange = rawStart >= 0 && rawEnd <= map.length;
    const start = map.toUtf16(rawStart);
    const end = map.toUtf16(rawEnd);
    out.push({ id: s.id, category: s.category, start, end, inRange });
  }
  return out;
}

export type Segment =
  | {
      kind: "text";
      start: number;
      end: number;
      text: string;
      /** Suggestions covering this stretch, most important first. Empty = plain text. */
      ids: string[];
      /** Category of ids[0], the one that styles the highlight. */
      category: Category | null;
    }
  | {
      kind: "point";
      /** Zero-length span (an insertion point, e.g. a missing comma). */
      at: number;
      ids: string[];
      category: Category;
    };

/**
 * Split `text` into contiguous segments so that overlapping, nested and
 * adjacent spans each render once, as plain text, with every covering
 * suggestion recorded. Concatenating the `text` of all "text" segments
 * always reproduces the input exactly.
 */
export function segment(text: string, spans: readonly ResolvedSpan[]): Segment[] {
  const len = text.length;
  const rank = new Map<string, number>();
  const sized = spans.map((s) => ({
    ...s,
    start: clamp(s.start, 0, len),
    end: clamp(s.end, 0, len),
  }));
  for (const s of sized) {
    // Lower rank sorts first: category priority, then the innermost (shortest) span.
    rank.set(s.id, CATEGORY_ORDER.indexOf(s.category) * 1e9 + (s.end - s.start));
  }
  const byRank = (a: string, b: string) =>
    (rank.get(a) ?? 0) - (rank.get(b) ?? 0) || (a < b ? -1 : a > b ? 1 : 0);
  const categoryOf = new Map(sized.map((s) => [s.id, s.category] as const));

  const points = new Map<number, string[]>();
  const opens = new Map<number, string[]>();
  const closes = new Map<number, string[]>();
  const bounds = new Set<number>([0, len]);
  const seen = new Set<string>();
  for (const s of sized) {
    if (seen.has(s.id)) continue; // duplicate ids would double-count
    seen.add(s.id);
    if (s.start === s.end) {
      push(points, s.start, s.id);
      bounds.add(s.start);
      continue;
    }
    push(opens, s.start, s.id);
    push(closes, s.end, s.id);
    bounds.add(s.start);
    bounds.add(s.end);
  }
  const sorted = [...bounds].sort((a, b) => a - b);
  const active = new Set<string>();
  const out: Segment[] = [];
  for (let k = 0; k < sorted.length; k++) {
    const at = sorted[k]!;
    for (const id of closes.get(at) ?? []) active.delete(id);
    const pts = points.get(at);
    if (pts) {
      const ids = [...pts].sort(byRank);
      out.push({ kind: "point", at, ids, category: categoryOf.get(ids[0]!)! });
    }
    for (const id of opens.get(at) ?? []) active.add(id);
    const next = sorted[k + 1];
    if (next === undefined || next === at) continue;
    const ids = [...active].sort(byRank);
    const prev = out[out.length - 1];
    if (ids.length === 0 && prev && prev.kind === "text" && prev.ids.length === 0) {
      prev.end = next;
      prev.text = text.slice(prev.start, next);
      continue;
    }
    out.push({
      kind: "text",
      start: at,
      end: next,
      text: text.slice(at, next),
      ids,
      category: ids.length ? categoryOf.get(ids[0]!)! : null,
    });
  }
  return out;
}

function push(m: Map<number, string[]>, k: number, v: string) {
  const list = m.get(k);
  if (list) list.push(v);
  else m.set(k, [v]);
}
