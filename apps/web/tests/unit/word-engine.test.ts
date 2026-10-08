import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeWordResponse, WordSuggestion } from "@researchly/contract";
import { analyzeWord, buildWordRequest, engineHealth, looksLikeAnalyzeWordResponse } from "@/lib/engine";
import { LOCAL_ENGINE_URL, reportProblemHref, SUPPORT_EMAIL } from "@/lib/config";
import { coverageSentences, heldBackSentence, listSentence, shownWordSuggestions, wordSummary } from "@/lib/word/view";
import { sugg } from "./helpers";

function wsugg(id: string, paragraph: number, start: number, extra: Partial<WordSuggestion> = {}): WordSuggestion {
  return {
    ...sugg(id, start, start + 3),
    location: { paragraph, start, end: start + 3, snippet: "abc", occurrence: 0, exact: true },
    ...extra,
  };
}

function response(suggestions: WordSuggestion[], extra: Partial<AnalyzeWordResponse> = {}): AnalyzeWordResponse {
  return {
    schema_version: "1",
    signed_in: false,
    warnings: [],
    suggestions,
    counts: {},
    hidden_preferences: 0,
    sections_detected: [],
    health: [],
    engine: { service_version: "0", core_version: "0", rules_loaded: 0 },
    elapsed_ms: 1,
    mode: "revise",
    hidden_by_mode: 0,
    coverage: { paragraphs: 3, table_paragraphs: 0, not_checked: ["footnotes"] },
    ...extra,
  };
}

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })),
  );
}

afterEach(() => vi.unstubAllGlobals());

const PARAS = [{ text: "A synthetic sentence.", style: "Normal", kind: "body" as const }];

describe("POST /v1/analyze-word", () => {
  it("always sends the mode, the preference switch, any mutes, the article type and whether the brief and the map are wanted", () => {
    expect(buildWordRequest({ paragraphs: PARAS, showPreferences: false, mode: "draft" })).toEqual({
      paragraphs: PARAS,
      options: { show_preferences: false, disabled_rules: [], mode: "draft", document_type: "auto", review: false, narrative: false },
    });
    expect(
      buildWordRequest({
        paragraphs: PARAS,
        showPreferences: true,
        mode: "revise",
        disabledRules: ["G101"],
        documentType: "thesis-chapter",
        review: true,
        narrative: true,
      }).options,
    ).toEqual({
      show_preferences: true,
      disabled_rules: ["G101"],
      mode: "revise",
      document_type: "thesis-chapter",
      review: true,
      narrative: true,
    });
  });

  it("goes to the chosen engine; no token to the local one (auth null), Bearer to the cloud", async () => {
    respond(response([]));
    await analyzeWord({ paragraphs: PARAS, showPreferences: false, mode: "revise" }, LOCAL_ENGINE_URL, null);
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toBe("http://localhost:3517/v1/analyze-word");
    expect((init!.headers as Record<string, string>).authorization).toBeUndefined();
    expect(init!.credentials).toBe("omit");

    respond(response([]));
    const auth = { token: async () => "tok-w", refresh: async () => ({ token: null }), signOutLocally: async () => {} };
    await analyzeWord({ paragraphs: PARAS, showPreferences: false, mode: "revise" }, "https://engine.test", auth);
    const [, init2] = vi.mocked(fetch).mock.calls[0]!;
    expect((init2!.headers as Record<string, string>).authorization).toBe("Bearer tok-w");
  });

  it("refuses an answer whose suggestions can't be found in Word", async () => {
    const good = response([wsugg("a", 0, 0)]);
    expect(looksLikeAnalyzeWordResponse(good)).toBe(true);
    expect(looksLikeAnalyzeWordResponse({ ...good, coverage: undefined })).toBe(false);
    const noLoc = { ...good, suggestions: [{ ...good.suggestions[0], location: undefined }] };
    expect(looksLikeAnalyzeWordResponse(noLoc)).toBe(false);
    const badOcc = { ...good, suggestions: [{ ...good.suggestions[0], location: { ...good.suggestions[0]!.location, occurrence: -1 } }] };
    expect(looksLikeAnalyzeWordResponse(badOcc)).toBe(false);
    respond(noLoc);
    const r = await analyzeWord({ paragraphs: PARAS, showPreferences: false, mode: "revise" }, "https://engine.test");
    expect(!r.ok && r.error.kind).toBe("bad_response");
  });

  it("maps sign_in_required to its own kind, with the engine's message", async () => {
    respond({ error: { code: "sign_in_required", message: "Sign in to check a whole chapter.", request_id: "r1" } }, 401);
    const r = await analyzeWord({ paragraphs: PARAS, showPreferences: false, mode: "revise" }, "https://engine.test");
    expect(!r.ok && r.error.kind).toBe("sign_in_required");
    expect(!r.ok && r.error.message).toBe("Sign in to check a whole chapter.");
  });
});

describe("GET /v1/health", () => {
  it("returns the tiers; no schema_version needed; no body sent", async () => {
    respond({ status: "degraded", tiers: [{ tier: "grammar", label: "Grammar", ok: false, state: "error" }], engine: {} });
    const r = await engineHealth("https://engine.test");
    expect(r.ok && r.data.tiers.map((t) => t.tier)).toEqual(["grammar"]);
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toBe("https://engine.test/v1/health");
    expect(init!.method).toBe("GET");
    expect(init!.body).toBeUndefined();
  });
  it("refuses a body that is not a health report", async () => {
    respond({ status: "fine" });
    expect((await engineHealth("https://engine.test")).ok).toBe(false);
  });
});

describe("taskpane view helpers", () => {
  it("orders by paragraph then position, and hides preferences unless asked", () => {
    const list = [wsugg("c", 2, 0), wsugg("b", 0, 9), wsugg("a", 0, 1), wsugg("p", 1, 0, { category: "preference" })];
    expect(shownWordSuggestions(response(list), false).map((s) => s.id)).toEqual(["a", "b", "c"]);
    expect(shownWordSuggestions(response(list), true).map((s) => s.id)).toEqual(["a", "b", "p", "c"]);
  });
  it("states coverage plainly", () => {
    expect(coverageSentences({ paragraphs: 1, table_paragraphs: 0, not_checked: [] })).toEqual({
      checked: "Checked 1 paragraph of the document body.",
      notChecked: null,
    });
    expect(
      coverageSentences({ paragraphs: 1200, table_paragraphs: 2, not_checked: ["footnotes", "endnotes", "headers and footers"] }),
    ).toEqual({
      checked: "Checked 1,200 paragraphs of the document body, 2 of them in tables.",
      notChecked: "Footnotes, endnotes and headers and footers were not checked.",
    });
    expect(coverageSentences({ paragraphs: 2, table_paragraphs: 0, not_checked: ["comments"] }).notChecked).toBe(
      "Comments was not checked.",
    );
    expect(listSentence(["a", "b"])).toBe("a and b");
  });
  it("says what Draft held back, and nothing when it held nothing", () => {
    expect(heldBackSentence(0)).toBeNull();
    expect(heldBackSentence(1)).toMatch(/^Draft held back 1 document-level suggestion,/);
    expect(heldBackSentence(3)).toMatch(/^Draft held back 3 document-level suggestions,/);
    expect(wordSummary(0)).toBe("Check complete. No suggestions.");
    expect(wordSummary(2)).toBe("Check complete. 2 suggestions.");
  });
});

describe("report a problem", () => {
  it("is a mailto to the owner with an encoded subject and no body", () => {
    expect(SUPPORT_EMAIL).toBe("amrit.mohapatra97@gmail.com");
    const href = reportProblemHref("Researchly Word add-in: a problem");
    expect(href).toBe("mailto:amrit.mohapatra97@gmail.com?subject=Researchly%20Word%20add-in%3A%20a%20problem");
    expect(href).not.toContain("body=");
  });
});
