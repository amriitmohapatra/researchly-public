/**
 * Client-side checks before a request is sent. Usability only: the engine
 * re-checks everything (browser validation is for usability, server
 * validation is for safety — ARCHITECTURE.md §6).
 */
import { MAX_CONTENT_CHARS, type Format } from "@researchly/contract";
import { codePointLength } from "./segments";

export type InputProblem = { kind: "empty" | "too_long"; message: string };

const fmt = new Intl.NumberFormat("en-GB");

export function validateContent(text: string): InputProblem | null {
  if (text.trim().length === 0) {
    return { kind: "empty", message: "Paste or type some text to check." };
  }
  // The engine counts Python characters (code points); so do we.
  const n = codePointLength(text);
  if (n > MAX_CONTENT_CHARS) {
    return {
      kind: "too_long",
      message: `This text has ${fmt.format(n)} characters; one check accepts up to ${fmt.format(
        MAX_CONTENT_CHARS,
      )}. Check one chapter or section at a time.`,
    };
  }
  return null;
}

export const FORMATS: readonly { value: Format; label: string }[] = [
  { value: "plain", label: "Plain text" },
  { value: "markdown", label: "Markdown" },
  { value: "latex", label: "LaTeX" },
];

export function isFormat(v: unknown): v is Format {
  return v === "plain" || v === "markdown" || v === "latex";
}
