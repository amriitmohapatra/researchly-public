/**
 * Which suggestions read the whole document (rule scope "document": figure
 * references, abbreviations defined once, numbering) and which judge one
 * sentence. A section view keeps the document-wide ones in their own group
 * so that narrowing to a section never loses them.
 *
 * The engine's rule registry (`GET /v1/rules`, no text sent) is the source
 * of truth. When it has not arrived, or does not list a rule (an older
 * engine), the ids the engine marks `scope="document"` today stand in.
 */
import { useMemo } from "react";
import type { RuleInfo, Scope } from "@researchly/contract";
import { useRegistry } from "./registry";

/** Rule scope by id, from the engine's registry. */
export type ScopeMap = ReadonlyMap<string, Scope>;

/** packages/core: every rule registered with scope="document" (X-series structure rules, F601/F612/F613, N101, W211, D902, AB802). */
const DOCUMENT_RULE_IDS: ReadonlySet<string> = new Set(["F601", "F612", "F613", "N101", "W211", "D902", "AB802"]);

export function scopeMap(rules: readonly RuleInfo[]): ScopeMap {
  return new Map(rules.map((r) => [r.id, r.scope ?? "sentence"]));
}

/** Whether a rule reads the whole document. `known` is the registry when it has arrived. */
export function isDocumentWide(ruleId: string, known: ScopeMap | null): boolean {
  const listed = known?.get(ruleId);
  if (listed) return listed === "document";
  return DOCUMENT_RULE_IDS.has(ruleId) || /^X\d/.test(ruleId);
}

export interface SectionSplit<T> {
  /** Sentence-level suggestions inside the chosen stretch. */
  inSection: T[];
  /** Document-wide suggestions (figure references, abbreviations defined once): shown under "Whole document". */
  wholeDocument: T[];
  /** Sentence-level suggestions elsewhere in the document, not shown. */
  elsewhere: number;
}

/** Split a list by a predicate for "inside the chosen section", keeping document-wide checks aside. */
export function splitForSection<T extends { rule_id: string }>(
  list: readonly T[],
  inside: (s: T) => boolean,
  known: ScopeMap | null,
): SectionSplit<T> {
  const out: SectionSplit<T> = { inSection: [], wholeDocument: [], elsewhere: 0 };
  for (const s of list) {
    if (isDocumentWide(s.rule_id, known)) out.wholeDocument.push(s);
    else if (inside(s)) out.inSection.push(s);
    else out.elsewhere++;
  }
  return out;
}

/* ---------- loading the registry (once per engine, shared: lib/registry.ts) ---------- */

/**
 * The engine's rule scopes, from the registry fetched once per engine URL
 * when `wanted` (after the first results). Null until then, or when the
 * engine has no registry (the local server): the built-in list stands in.
 */
export function useRuleScopes(engineUrl: string | null, wanted: boolean): ScopeMap | null {
  const registry = useRegistry(engineUrl, wanted);
  return useMemo(() => (registry ? scopeMap(registry.rules) : null), [registry]);
}
