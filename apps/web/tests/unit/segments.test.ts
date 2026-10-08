import { describe, expect, it } from "vitest";
import { buildOffsetMap, codePointLength, resolveSpans, segment, type Segment } from "@/lib/segments";
import { pyIndex, pySlice, sugg } from "./helpers";

type TextSeg = Extract<Segment, { kind: "text" }>;
const texts = (segs: Segment[]) => segs.filter((s): s is TextSeg => s.kind === "text");
const joined = (segs: Segment[]) => texts(segs).map((s) => s.text).join("");

function segmentOf(text: string, ...ss: ReturnType<typeof sugg>[]) {
  return segment(text, resolveSpans(text, ss));
}

describe("codePointLength (Python len)", () => {
  it("counts BMP characters one each", () => {
    expect(codePointLength("")).toBe(0);
    expect(codePointLength("naïve café")).toBe(10);
  });
  it("counts a surrogate pair as one character", () => {
    expect(codePointLength("a😀b")).toBe(3);
    expect("a😀b".length).toBe(4);
    expect(codePointLength("𝑅ₜ")).toBe(2); // U+1D445 is non-BMP, U+209C is BMP
  });
  it("counts a lone surrogate as one character, like Python", () => {
    expect(codePointLength("\uD800x")).toBe(2);
    expect(codePointLength("x\uDC00")).toBe(2);
  });
  it("counts each code point of a ZWJ sequence (Python does too)", () => {
    const family = "👩‍👩‍👧";
    expect(codePointLength(family)).toBe(Array.from(family).length);
  });
});

describe("buildOffsetMap", () => {
  it("is the identity for BMP-only text", () => {
    const m = buildOffsetMap("hello");
    expect(m.length).toBe(5);
    expect([0, 1, 5].map(m.toUtf16)).toEqual([0, 1, 5]);
  });
  it("shifts offsets after each non-BMP character", () => {
    const m = buildOffsetMap("😀a😀b");
    expect(m.length).toBe(4);
    expect([0, 1, 2, 3, 4].map(m.toUtf16)).toEqual([0, 2, 3, 5, 6]);
  });
  it("clamps out-of-range and non-integer indices", () => {
    const m = buildOffsetMap("😀a");
    expect(m.toUtf16(-3)).toBe(0);
    expect(m.toUtf16(99)).toBe(3);
    expect(m.toUtf16(1.7)).toBe(2);
    expect(m.toUtf16(Number.NaN)).toBe(0);
  });
});

describe("resolveSpans: engine code points → JS UTF-16", () => {
  it("places a span after an emoji", () => {
    const text = "Mosquito 🦟 bites spread dengue.";
    const start = pyIndex(text, "dengue");
    const s = sugg("a", start, start + 6, "correction", { text: "dengue" });
    const [r] = resolveSpans(text, [s]);
    expect(start).toBe(text.indexOf("dengue") - 1); // the emoji counts once in Python
    expect(text.slice(r!.start, r!.end)).toBe("dengue");
    expect(r!.inRange).toBe(true);
  });

  it("places a span after a non-BMP mathematical letter", () => {
    const text = "We estimated 𝑅ₜ daily; 𝑅ₜ was estimated weekly.";
    const start = pyIndex(text, "was estimated");
    const [r] = resolveSpans(text, [sugg("a", start, start + 13, "improvement", { text: "was estimated" })]);
    expect(text.slice(r!.start, r!.end)).toBe("was estimated");
  });

  it("places a span that covers a non-BMP character itself", () => {
    const text = "Vector: 🦟 (Aedes).";
    const start = pyIndex(text, "🦟");
    expect(pySlice(text, start, start + 1)).toBe("🦟");
    const [r] = resolveSpans(text, [sugg("a", start, start + 1)]);
    expect(text.slice(r!.start, r!.end)).toBe("🦟");
    expect(r!.end - r!.start).toBe(2);
  });

  it("handles many non-BMP characters before the span", () => {
    const text = "😀😀😀 𝑥𝑦𝑧 target";
    const start = pyIndex(text, "target");
    const [r] = resolveSpans(text, [sugg("a", start, start + 6)]);
    expect(text.slice(r!.start, r!.end)).toBe("target");
  });

  it("keeps BMP-only text unchanged", () => {
    const text = "The the cat.";
    const [r] = resolveSpans(text, [sugg("a", 0, 7, "correction", { text: "The the" })]);
    expect([r!.start, r!.end]).toEqual([0, 7]);
  });

  it("falls back to UTF-16 offsets only when they match the flagged text and code points do not", () => {
    const text = "😀 alpha beta";
    const utf16 = text.indexOf("beta");
    const [r] = resolveSpans(text, [sugg("a", utf16, utf16 + 4, "improvement", { text: "beta" })]);
    expect(text.slice(r!.start, r!.end)).toBe("beta");
  });

  it("drops spans that start beyond the end of the text", () => {
    expect(resolveSpans("short", [sugg("a", 10, 12)])).toEqual([]);
  });

  it("clamps spans that run past the end and marks them out of range", () => {
    const [r] = resolveSpans("short", [sugg("a", 2, 50)]);
    expect([r!.start, r!.end, r!.inRange]).toEqual([2, 5, false]);
  });

  it("clamps a negative start", () => {
    const [r] = resolveSpans("short", [sugg("a", -4, 2)]);
    expect([r!.start, r!.end, r!.inRange]).toEqual([0, 2, false]);
  });

  it("swaps a reversed span", () => {
    const [r] = resolveSpans("abcdef", [sugg("a", 4, 1)]);
    expect([r!.start, r!.end]).toEqual([1, 4]);
  });

  it("ignores non-finite offsets", () => {
    expect(resolveSpans("abc", [sugg("a", Number.NaN, 2)])).toEqual([]);
  });
});

describe("segment", () => {
  it("returns one plain segment when there are no spans", () => {
    const segs = segmentOf("Plain text.");
    expect(segs).toEqual([{ kind: "text", start: 0, end: 11, text: "Plain text.", ids: [], category: null }]);
  });

  it("returns nothing for empty text", () => {
    expect(segmentOf("")).toEqual([]);
  });

  it("splits overlapping spans into three stretches", () => {
    const text = "0123456789abcdefghij";
    const segs = texts(segmentOf(text, sugg("A", 0, 10, "improvement"), sugg("B", 5, 15, "improvement")));
    expect(segs.map((s) => [s.start, s.end, s.ids])).toEqual([
      [0, 5, ["A"]],
      [5, 10, ["A", "B"]],
      [10, 15, ["B"]],
      [15, 20, []],
    ]);
    expect(joined(segmentOf(text, sugg("A", 0, 10), sugg("B", 5, 15)))).toBe(text);
  });

  it("puts the more important category first inside a nested span", () => {
    const text = "In order to understand the dynamics";
    const segs = texts(segmentOf(text, sugg("outer", 0, 35, "convention"), sugg("inner", 3, 8, "correction")));
    const middle = segs.find((s) => s.start === 3)!;
    expect(middle.ids).toEqual(["inner", "outer"]);
    expect(middle.category).toBe("correction");
    expect(segs.find((s) => s.start === 0)!.category).toBe("convention");
  });

  it("puts the innermost span first when categories tie", () => {
    const text = "abcdefghij";
    const segs = texts(segmentOf(text, sugg("long", 0, 10, "improvement"), sugg("short", 2, 4, "improvement")));
    expect(segs.find((s) => s.start === 2)!.ids).toEqual(["short", "long"]);
  });

  it("keeps adjacent spans separate with no gap", () => {
    const text = "aaaaabbbbb";
    const segs = texts(segmentOf(text, sugg("A", 0, 5, "correction"), sugg("B", 5, 10, "convention")));
    expect(segs.map((s) => [s.start, s.end, s.ids])).toEqual([
      [0, 5, ["A"]],
      [5, 10, ["B"]],
    ]);
  });

  it("handles identical spans as one stretch with both ids", () => {
    const segs = texts(segmentOf("abc", sugg("A", 0, 3, "preference"), sugg("B", 0, 3, "correction")));
    expect(segs).toHaveLength(1);
    expect(segs[0]!.ids).toEqual(["B", "A"]);
  });

  it("renders a zero-length span as an insertion point between text", () => {
    const text = "However the results";
    const segs = segmentOf(text, sugg("comma", 7, 7, "correction"));
    expect(segs.map((s) => s.kind)).toEqual(["text", "point", "text"]);
    expect(segs[1]).toEqual({ kind: "point", at: 7, ids: ["comma"], category: "correction" });
    expect(joined(segs)).toBe(text);
  });

  it("renders insertion points at the very start and end", () => {
    const text = "abc";
    const segs = segmentOf(text, sugg("s", 0, 0), sugg("e", 3, 3));
    expect(segs.map((s) => s.kind)).toEqual(["point", "text", "point"]);
  });

  it("places an insertion point inside another span", () => {
    const segs = segmentOf("abcdef", sugg("outer", 0, 6, "convention"), sugg("p", 3, 3, "correction"));
    expect(segs.map((s) => (s.kind === "point" ? `p@${s.at}` : `${s.start}-${s.end}:${s.ids}`))).toEqual([
      "0-3:outer",
      "p@3",
      "3-6:outer",
    ]);
  });

  it("ignores a duplicated suggestion id", () => {
    const segs = texts(segmentOf("abcdef", sugg("A", 0, 3), sugg("A", 0, 3)));
    expect(segs[0]!.ids).toEqual(["A"]);
  });

  it("merges neighbouring plain stretches", () => {
    // A span dropped as out of range must not leave a seam in the plain text.
    const segs = segmentOf("abcdef", sugg("gone", 50, 60));
    expect(segs).toHaveLength(1);
  });

  it("segments correctly after emoji, with highlights on the right characters", () => {
    const text = "🦟 Dengue is clearly proven 😀 to spread.";
    const a = pyIndex(text, "clearly proven");
    const b = pyIndex(text, "spread");
    const segs = texts(segmentOf(text, sugg("A", a, a + 14, "improvement"), sugg("B", b, b + 6, "convention")));
    expect(segs.filter((s) => s.ids.length).map((s) => s.text)).toEqual(["clearly proven", "spread"]);
    expect(joined(segs)).toBe(text);
  });

  it("satisfies its invariants on random input (property test)", () => {
    const alphabet = ["a", "b", " ", "😀", "𝑅", "é", "\n", "🦟"];
    let seed = 42;
    const rnd = (n: number) => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % n;
    };
    const cats = ["correction", "improvement", "convention", "preference"] as const;
    for (let round = 0; round < 300; round++) {
      const chars = Array.from({ length: rnd(30) }, () => alphabet[rnd(alphabet.length)]!);
      const text = chars.join("");
      const n = chars.length;
      const ss = Array.from({ length: rnd(6) }, (_, i) => {
        const s = rnd(n + 1);
        const e = s + rnd(n + 1 - s);
        return sugg(`id${i}`, s, e, cats[rnd(4)]!);
      });
      const segs = segmentOf(text, ...ss);
      // 1. the text is reproduced exactly, in order, without gaps
      expect(joined(segs)).toBe(text);
      let pos = 0;
      for (const t of texts(segs)) {
        expect(t.start).toBe(pos);
        expect(t.end).toBeGreaterThan(t.start);
        pos = t.end;
      }
      // 2. every stretch is covered by exactly the spans that contain it (oracle in code points)
      for (const t of texts(segs)) {
        const cpStart = Array.from(text.slice(0, t.start)).length;
        const cpEnd = Array.from(text.slice(0, t.end)).length;
        const expected = ss
          .filter((s) => s.span.start < s.span.end && s.span.start <= cpStart && s.span.end >= cpEnd)
          .map((s) => s.id)
          .sort();
        expect([...t.ids].sort()).toEqual(expected);
      }
      // 3. every highlighted stretch slices to the Python slice of its spans
      for (const s of ss.filter((x) => x.span.end > x.span.start)) {
        const covered = texts(segs)
          .filter((t) => t.ids.includes(s.id))
          .map((t) => t.text)
          .join("");
        expect(covered).toBe(pySlice(text, s.span.start, s.span.end));
      }
      // 4. every zero-length span appears as exactly one point
      for (const s of ss.filter((x) => x.span.end === x.span.start)) {
        expect(segs.filter((g) => g.kind === "point" && g.ids.includes(s.id))).toHaveLength(1);
      }
    }
  });
});
