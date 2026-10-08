import { describe, expect, it } from "vitest";
import { happyResponse, SAMPLE_TEXT, withPreferencesResponse } from "../../e2e/fixtures";
import { resolveSpans } from "@/lib/segments";
import { pySlice } from "./helpers";

describe("e2e fixtures are faithful to the engine's offsets", () => {
  it("every span, read as Python code points, slices to its flagged text", () => {
    for (const s of withPreferencesResponse.suggestions) {
      expect(pySlice(SAMPLE_TEXT, s.span.start, s.span.end)).toBe(s.text);
    }
  });

  it("the sample really exercises non-BMP offsets (UTF-16 slicing would be wrong)", () => {
    const shifted = happyResponse.suggestions.filter(
      (s) => s.text && SAMPLE_TEXT.slice(s.span.start, s.span.end) !== s.text,
    );
    expect(shifted.length).toBeGreaterThan(3);
  });

  it("resolveSpans places every fixture span on its flagged text", () => {
    for (const r of resolveSpans(SAMPLE_TEXT, withPreferencesResponse.suggestions)) {
      const s = withPreferencesResponse.suggestions.find((x) => x.id === r.id)!;
      expect(SAMPLE_TEXT.slice(r.start, r.end)).toBe(s.text);
    }
  });
});
