/**
 * Uploaded files: client-side checks before sending, and where in a
 * multi-file project a suggestion sits. Pure and unit-tested.
 *
 * Offsets: like suggestion spans, `Segment.start/end/source_start` are
 * Unicode code points into `document.text` (Python str indices), so lines
 * are counted after converting with lib/segments' offset map.
 */
import { MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS, type Segment } from "@researchly/contract";
import { UPLOAD_TYPES_SENTENCE, formatBytes } from "./errors";
import { buildOffsetMap } from "./segments";

export type FileProblem = { kind: "type" | "size" | "empty"; message: string };

/** The `accept` attribute for the file picker. */
export const ACCEPT_ATTR = UPLOAD_EXTENSIONS.join(",");

export function extensionOf(name: string): string {
  const m = /\.[^./\\]+$/.exec(name);
  return m ? m[0].toLowerCase() : "";
}

/** Usability only: the engine decides what it can read (and re-checks the size before reading). */
export function checkFile(file: { name: string; size: number }): FileProblem | null {
  const ext = extensionOf(file.name);
  if (!(UPLOAD_EXTENSIONS as readonly string[]).includes(ext)) {
    return {
      kind: "type",
      message: `${ext ? `${ext} files can't be checked.` : "This file has no extension."} Researchly reads ${UPLOAD_TYPES_SENTENCE}`,
    };
  }
  if (file.size === 0) return { kind: "empty", message: "This file is empty." };
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      kind: "size",
      message: `This file is ${formatBytes(file.size)}; files up to ${formatBytes(MAX_UPLOAD_BYTES)} can be checked. Try one chapter at a time.`,
    };
  }
  return null;
}

/** How the file was read, in words. */
export function formatLabel(format: string): string {
  switch (format) {
    case "docx":
      return "Word document";
    case "latex":
      return "LaTeX";
    case "markdown":
      return "Markdown";
    case "plain":
      return "Plain text";
    default:
      return format;
  }
}

export interface Location {
  path: string;
  /** 1-based line within that file. */
  line: number;
}

/** Whether locations are worth showing: only when the text came from more than one file. */
export function isMultiFile(segments: readonly Segment[]): boolean {
  return new Set(segments.map((s) => s.path)).size > 1;
}

/**
 * Builds a lookup from a code-point offset in `text` to (file, line).
 *
 * The segment containing the offset names the file. Its line is the number of
 * newlines before the offset within that segment, plus the lines of the
 * earlier piece of the same inclusion of that file: a main.tex split around an
 * \input appears as several segments, each continuing where the last stopped.
 * A segment starting at source offset 0 starts a new inclusion (a file
 * \input twice is counted from line 1 both times). Text the expansion dropped
 * between pieces, such as the `\input{…}` command itself, is assumed to hold
 * no line breaks.
 *
 * Newlines are counted once, up front, so each lookup is O(log n).
 */
export function buildLocator(text: string, segments: readonly Segment[]): (offset: number) => Location | null {
  const map = buildOffsetMap(text);
  const sorted = [...segments]
    .filter((s) => Number.isFinite(s.start) && Number.isFinite(s.end) && s.end >= s.start)
    .sort((a, b) => a.start - b.start);
  // UTF-16 positions of every "\n", ascending.
  const breaks: number[] = [];
  for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1)) breaks.push(i);
  /** Number of newlines at UTF-16 positions < pos. */
  const before = (pos: number) => {
    let lo = 0;
    let hi = breaks.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (breaks[mid]! < pos) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };
  const newlines = (from: number, to: number) => before(map.toUtf16(to)) - before(map.toUtf16(from));

  // In document order: each piece continues the most recent earlier piece of
  // the same file that it follows in the source.
  const base = new Map<Segment, number>();
  const last = new Map<string, { seg: Segment; endLine: number }>();
  for (const s of sorted) {
    const prev = last.get(s.path);
    const continues = prev && s.source_start > 0 && s.source_start >= prev.seg.source_start + (prev.seg.end - prev.seg.start);
    const b = continues ? prev.endLine : 0;
    base.set(s, b);
    last.set(s.path, { seg: s, endLine: b + newlines(s.start, s.end) });
  }

  return (offset: number) => {
    if (!Number.isFinite(offset) || sorted.length === 0) return null;
    // Binary search: the last segment starting at or before the offset.
    let lo = 0;
    let hi = sorted.length - 1;
    let hit = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid]!.start <= offset) {
        hit = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    if (hit < 0) return null;
    const seg = sorted[hit]!;
    // Past the end: in a gap no file covers. Exactly at the end (a zero-length
    // span after the last word of a file) still belongs to it.
    if (offset > seg.end) return null;
    return { path: seg.path, line: 1 + (base.get(seg) ?? 0) + newlines(seg.start, offset) };
  };
}
