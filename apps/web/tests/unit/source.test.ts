import { describe, expect, it } from "vitest";
import type { Segment } from "@researchly/contract";
import { buildLocator, formatLabel, isMultiFile } from "@/lib/source";
import { pyIndex } from "./helpers";

const seg = (path: string, start: number, end: number, source_start = 0): Segment => ({ path, start, end, source_start });

describe("segment → file lookup", () => {
  const MAIN = "\\documentclass{article}\n\\begin{document}\nIntro line.\n";
  const METHODS = "\\section{Methods}\nWe fitted the model.\nThe the data.\n";
  // The expansion drops only the `\input{methods}` command; the line break after it stays in main.tex.
  const TAIL = "\nClosing line.\n\\end{document}\n";
  // main.tex is split around \input{methods}: two segments of the same file.
  const text = MAIN + METHODS + TAIL;
  const segments = [
    seg("main.tex", 0, MAIN.length, 0),
    seg("sections/methods.tex", MAIN.length, MAIN.length + METHODS.length, 0),
    seg("main.tex", MAIN.length + METHODS.length, text.length, MAIN.length + "\\input{methods}".length),
  ];
  const locate = buildLocator(text, segments);

  it("names the file and the line within it", () => {
    expect(locate(text.indexOf("Intro"))).toEqual({ path: "main.tex", line: 3 });
    expect(locate(text.indexOf("\\section"))).toEqual({ path: "sections/methods.tex", line: 1 });
    expect(locate(text.indexOf("The the"))).toEqual({ path: "sections/methods.tex", line: 3 });
  });

  it("continues a file's line count across its segments", () => {
    // main.tex: 1 documentclass, 2 begin, 3 Intro, 4 \input{methods}, 5 Closing, 6 end.
    expect(locate(text.indexOf("Closing"))).toEqual({ path: "main.tex", line: 5 });
    expect(locate(text.indexOf("\\end{document}"))).toEqual({ path: "main.tex", line: 6 });
  });

  it("a file included twice is counted from line 1 each time", () => {
    const ABBR = "\\newcommand{\\Rt}{R_t}\nSecond line.\n";
    const A = "Chapter one.\n";
    const B = "Chapter two.\n";
    const t = A + ABBR + B + ABBR;
    const segs = [
      seg("main.tex", 0, A.length, 0),
      seg("abbrev.tex", A.length, A.length + ABBR.length, 0),
      seg("main.tex", A.length + ABBR.length, A.length + ABBR.length + B.length, A.length + 14),
      seg("abbrev.tex", A.length + ABBR.length + B.length, t.length, 0),
    ];
    const loc = buildLocator(t, segs);
    expect(loc(t.indexOf("Second line."))).toEqual({ path: "abbrev.tex", line: 2 });
    expect(loc(t.lastIndexOf("Second line."))).toEqual({ path: "abbrev.tex", line: 2 });
    expect(loc(t.indexOf("Chapter two."))).toEqual({ path: "main.tex", line: 2 });
  });

  it("uses code points, like the engine (emoji and 𝑅 before the span)", () => {
    const a = "Alpha 🦟 line\nsecond 𝑅ₜ line\n";
    const b = "Beta file\nhere is 𝑅 the target\n";
    const t = a + b;
    const aLen = Array.from(a).length;
    const loc = buildLocator(t, [seg("a.tex", 0, aLen), seg("b.tex", aLen, Array.from(t).length)]);
    expect(loc(pyIndex(t, "target"))).toEqual({ path: "b.tex", line: 2 });
    expect(loc(pyIndex(t, "second"))).toEqual({ path: "a.tex", line: 2 });
  });

  it("an offset at the very end belongs to the last file; outside every segment is null", () => {
    expect(locate(text.length)?.path).toBe("main.tex");
    expect(buildLocator("abc", [])(1)).toBeNull();
    expect(buildLocator("abcdef", [seg("x.tex", 2, 4)])(0)).toBeNull();
    expect(buildLocator("abcdef", [seg("x.tex", 2, 4)])(5)).toBeNull();
    expect(locate(Number.NaN)).toBeNull();
  });

  it("only multi-file uploads get locations", () => {
    expect(isMultiFile(segments)).toBe(true);
    expect(isMultiFile([seg("chapter.md", 0, 10)])).toBe(false);
    expect(isMultiFile([seg("main.tex", 0, 5), seg("main.tex", 5, 10, 20)])).toBe(false);
  });

  it("labels formats in words", () => {
    expect(formatLabel("docx")).toBe("Word document");
    expect(formatLabel("latex")).toBe("LaTeX");
  });
});
