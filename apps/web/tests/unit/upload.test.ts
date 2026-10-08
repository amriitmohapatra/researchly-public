import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_BYTES } from "@researchly/contract";
import { buildFileRequest, encodeFilename } from "@/lib/engine";
import { checkFile, extensionOf } from "@/lib/source";

const file = (name: string, body = "x") => new File([body], name, { type: "application/octet-stream" });

describe("upload request builder", () => {
  it("sends the raw file as octet-stream with the name and options in headers", () => {
    const f = file("chapter-4.docx", "PK...");
    const r = buildFileRequest(f, { showPreferences: true }, null);
    expect(r.method).toBe("POST");
    expect(r.body).toBe(f);
    expect(r.headers).toEqual({
      "content-type": "application/octet-stream",
      accept: "application/json",
      "x-researchly-filename": "chapter-4.docx",
      "x-researchly-options": '{"show_preferences":true,"document_type":"auto","review":false,"narrative":false}',
    });
  });

  it("carries the article type, the brief and the narrative-map requests in the options header (S4)", () => {
    const r = buildFileRequest(
      file("chapter-4.docx"),
      { showPreferences: false, documentType: "thesis-chapter", review: true, narrative: true },
      null,
    );
    expect(JSON.parse(r.headers["x-researchly-options"]!)).toEqual({
      show_preferences: false,
      document_type: "thesis-chapter",
      review: true,
      narrative: true,
    });
  });

  it("adds the bearer token only when signed in", () => {
    expect(buildFileRequest(file("a.md"), { showPreferences: false }, "tok").headers.authorization).toBe("Bearer tok");
    expect(buildFileRequest(file("a.md"), { showPreferences: false }, null).headers).not.toHaveProperty("authorization");
  });

  it("percent-encodes non-ASCII names (a header can't carry them as-is)", () => {
    expect(encodeFilename("Kapitel_ü.docx")).toBe("Kapitel_%C3%BC.docx");
    expect(encodeFilename("第四章 方法.tex")).toBe("%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%96%B9%E6%B3%95.tex");
    expect(encodeFilename("chapter 4 (final).md")).toBe("chapter%204%20(final).md");
    expect(decodeURIComponent(encodeFilename("Résumé 𝑅ₜ.md"))).toBe("Résumé 𝑅ₜ.md");
    // Every byte is header-safe ASCII.
    expect(encodeFilename("naïve—ünïcode.zip")).toMatch(/^[\x21-\x7e]+$/);
  });

  it("keeps only the base name and survives names that can't be encoded or are huge", () => {
    expect(encodeFilename("C:\\Users\\me\\thesis.tex")).toBe("thesis.tex");
    expect(encodeFilename("bad\uD800half.md")).toBe("upload.md"); // a lone surrogate
    expect(encodeFilename(`${"ü".repeat(400)}.docx`)).toBe("upload.docx");
    expect(encodeFilename("")).toBe("upload");
  });
});

describe("client-side file checks (usability only)", () => {
  it("knows the accepted extensions, case-insensitively", () => {
    for (const n of ["a.docx", "a.tex", "a.zip", "a.md", "a.qmd", "a.Rmd", "a.RMD", "a.txt"]) {
      expect(checkFile({ name: n, size: 10 }), n).toBeNull();
    }
    expect(extensionOf("thesis.final.TEX")).toBe(".tex");
    expect(extensionOf("Makefile")).toBe("");
  });

  it("refuses other types and says what is accepted", () => {
    const p = checkFile({ name: "figure.pdf", size: 10 });
    expect(p?.kind).toBe("type");
    expect(p?.message).toContain(".pdf files can't be checked");
    expect(p?.message).toContain(".docx");
    expect(checkFile({ name: "README", size: 10 })?.message).toContain("no extension");
  });

  it("refuses empty files and files over 25 MB", () => {
    expect(checkFile({ name: "a.md", size: 0 })?.kind).toBe("empty");
    expect(checkFile({ name: "a.docx", size: MAX_UPLOAD_BYTES })).toBeNull();
    const big = checkFile({ name: "a.docx", size: MAX_UPLOAD_BYTES + 1 });
    expect(big?.kind).toBe("size");
    expect(big?.message).toContain("25 MB");
  });
});
