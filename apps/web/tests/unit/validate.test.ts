import { describe, expect, it } from "vitest";
import { MAX_CONTENT_CHARS } from "@researchly/contract";
import { isFormat, validateContent } from "@/lib/validate";

describe("client-side validation", () => {
  it("rejects empty and whitespace-only text", () => {
    expect(validateContent("")?.kind).toBe("empty");
    expect(validateContent("  \n\t ")?.kind).toBe("empty");
  });

  it("accepts text at exactly the limit, counted in code points like the engine", () => {
    expect(validateContent("a".repeat(MAX_CONTENT_CHARS))).toBeNull();
    // MAX emoji = 2×MAX UTF-16 units, but still MAX characters to Python.
    expect(validateContent("😀".repeat(MAX_CONTENT_CHARS))).toBeNull();
  });

  it("rejects text over the limit", () => {
    const p = validateContent("a".repeat(MAX_CONTENT_CHARS + 1));
    expect(p?.kind).toBe("too_long");
    expect(p?.message).toContain("1,000,001");
  });

  it("knows the three S1 formats", () => {
    expect(["plain", "markdown", "latex"].every(isFormat)).toBe(true);
    expect(isFormat("docx")).toBe(false);
    expect(isFormat(null)).toBe(false);
  });
});
