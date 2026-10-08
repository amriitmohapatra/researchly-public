import { describe, expect, it } from "vitest";
import type { WordLocation } from "@researchly/contract";
import {
  APPROXIMATE_APPLY_MESSAGE,
  applyReplacement,
  CHANGED_MESSAGE,
  codePointSlice,
  countOccurrences,
  FIELD_MESSAGE,
  FIELD_UNKNOWN_MESSAGE,
  NOT_FOUND_MESSAGE,
  readParagraphs,
  readSelectionParagraph,
  RANGE_CHANGED_MESSAGE,
  RESTORE_FAILED_MESSAGE,
  restoreHistory,
  selectSpan,
  toWordParagraph,
  UNKNOWN_MESSAGE,
  waitForOffice,
  WORD_FAILED_MESSAGE,
  type OfficeApi,
} from "@/lib/word/office";
import { installFakeOffice, type FakeWordConfig } from "../../e2e/fake-office";

/** Synthetic sentences written for these tests. */
const PARAS = [
  { text: "Methods", styleBuiltIn: "Heading1" },
  { text: "Then the the model was fitted and the the priors were weak.", styleBuiltIn: "Normal" },
  { text: "Region", tableNestingLevel: 1 },
];

/** Word after start-up: `Word` defined, as it is once Office.onReady has resolved. */
function fake(config: Partial<FakeWordConfig> = {}) {
  const t = fresh(config);
  t.target.Word = t.target.__fakeWordNamespace;
  return t;
}

/** Word as office.js leaves it on first run: `Office` only; `Word` arrives with onReady. */
function fresh(config: Partial<FakeWordConfig> = {}) {
  const target: Record<string, unknown> = {};
  const state = installFakeOffice(target, { paragraphs: PARAS, ...config });
  const api = target as unknown as OfficeApi;
  const wordApi = () => (target.Word ? api : null);
  return { api, state, target, wordApi };
}

/** Where the engine would locate the n-th "the the" (0-based) in paragraph 1. */
function loc(occurrence: number, extra: Partial<WordLocation> = {}): WordLocation {
  const text = PARAS[1]!.text;
  let at = -1;
  for (let i = 0; i <= occurrence; i++) at = text.indexOf("the the", at + 1);
  return { paragraph: 1, start: at, end: at + 7, snippet: "the the", occurrence, exact: true, ...extra };
}

describe("reading paragraphs", () => {
  it("sends text, the built-in style where there is one, and marks table cells", async () => {
    const { api } = fake();
    expect(await readParagraphs(api)).toEqual([
      { text: "Methods", style: "Heading1", kind: "body" },
      { text: PARAS[1]!.text, style: "Normal", kind: "body" },
      { text: "Region", style: "Normal", kind: "table" },
    ]);
  });

  it("falls back to the custom style name, and clamps it to the contract's 200 characters", () => {
    expect(toWordParagraph({ text: "x", style: "Thesis Heading", styleBuiltIn: "Other" }).style).toBe("Thesis Heading");
    expect(toWordParagraph({ text: "x", style: "s".repeat(300) }).style).toHaveLength(200);
    expect(toWordParagraph({ text: null, tableNestingLevel: 2 })).toEqual({ text: "", style: "", kind: "table" });
  });
});

describe("text helpers", () => {
  it("slices by code point, like Python", () => {
    expect(codePointSlice("R𝑡 was high", 0, 2)).toBe("R𝑡");
    expect(codePointSlice("R𝑡 was high", 3, 6)).toBe("was");
  });
  it("counts non-overlapping matches, like Python's str.count", () => {
    expect(countOccurrences("aaaa", "aa")).toBe(2);
    expect(countOccurrences("the the the", "the")).toBe(3);
    expect(countOccurrences("abc", "")).toBe(0);
  });
});

describe("selecting a suggestion", () => {
  it("selects match number `occurrence`, not the first copy of a repeated phrase", async () => {
    const { api, state } = fake();
    const r = await selectSpan(api, loc(1));
    expect(r).toEqual({ ok: true, approximate: false });
    expect(state.selection).toMatchObject({ paragraph: 1, start: loc(1).start, text: "the the" });
    expect(state.selection!.start).toBeGreaterThan(30);
  });

  it("says when the match is approximate (a long span located by its start)", async () => {
    const { api, state } = fake();
    const r = await selectSpan(api, { paragraph: 1, start: 0, end: 30, snippet: "Then the the model", occurrence: 0, exact: false });
    expect(r).toEqual({ ok: true, approximate: true });
    expect(state.selection!.text).toBe("Then the the model");
  });

  it("refuses when the paragraph no longer holds the text at that place", async () => {
    const { api, state } = fake();
    state.paragraphs[1]!.text = `Edited. ${state.paragraphs[1]!.text}`;
    expect(await selectSpan(api, loc(0))).toEqual({ ok: false, message: CHANGED_MESSAGE });
    expect(state.selection).toBeNull();
  });

  it("refuses when the paragraph is gone", async () => {
    const { api } = fake();
    expect(await selectSpan(api, { ...loc(0), paragraph: 9 })).toEqual({ ok: false, message: CHANGED_MESSAGE });
  });

  it("refuses when Word finds a different number of matches than the engine counted", async () => {
    const { api } = fake();
    // matchCase search finds "the the" twice; claim a third.
    expect(await selectSpan(api, { ...loc(1), occurrence: 2 })).toEqual({ ok: false, message: NOT_FOUND_MESSAGE });
  });
});

describe("applying a fix", () => {
  it("with WordApi 1.4: replaces only that copy, as a tracked change, and restores Track Changes", async () => {
    const { api, state } = fake({ api14: true, trackingMode: "Off" });
    const r = await applyReplacement(api, loc(1), "the");
    expect(r).toEqual({ ok: true, outcome: "applied", tracked: true });
    expect(state.paragraphs[1]!.text).toBe("Then the the model was fitted and the priors were weak.");
    expect(state.edits).toEqual([expect.objectContaining({ before: "the the", text: "the", tracked: true })]);
    expect(state.trackingWrites).toEqual(["TrackAll", "Off"]);
    expect(state.trackingMode).toBe("Off");
  });

  it("leaves Track Changes alone when the writer already had it on", async () => {
    const { api, state } = fake({ trackingMode: "TrackAll" });
    expect(await applyReplacement(api, loc(0), "the")).toMatchObject({ ok: true, outcome: "applied", tracked: true });
    expect(state.trackingWrites).toEqual([]);
  });

  it("without WordApi 1.4: never sets changeTrackingMode (it would silently fail the batch) and edits directly", async () => {
    const { api, state } = fake({ api14: false });
    const r = await applyReplacement(api, loc(0), "the");
    expect(r).toEqual({ ok: true, outcome: "applied", tracked: false });
    expect(state.trackingWrites).toEqual([]);
    expect(state.failedBatches).toBe(0);
    expect(state.edits).toEqual([expect.objectContaining({ tracked: false, text: "the" })]);
  });

  it("the fake really does fail a batch that sets tracking on old Word (so the test above means something)", async () => {
    const { api, state } = fake({ api14: false });
    await expect(
      api.Word.run(async (ctx) => {
        ctx.document.changeTrackingMode = "TrackAll";
        await ctx.sync();
      }),
    ).rejects.toThrow(/GeneralException/);
    expect(state.failedBatches).toBe(1);
  });

  it("refuses a range whose text changed after it was found", async () => {
    const { api, state } = fake();
    const wordRun = api.Word.run.bind(api.Word);
    // Word re-reads the range and finds different text (e.g. edited mid-batch by co-authoring).
    api.Word.run = (batch) =>
      wordRun(async (ctx) => {
        const paras = ctx.document.body.paragraphs;
        const origLoad = paras.load.bind(paras);
        paras.load = (p) => {
          origLoad(p);
          const para = paras.items[1]!;
          const search = para.search.bind(para);
          para.search = (needle, o) => {
            const res = search(needle, o);
            for (const r of res.items) r.load = () => void (r.text = "changed");
            return res;
          };
        };
        return batch(ctx);
      });
    expect(await applyReplacement(api, loc(0), "the")).toEqual({ ok: false, outcome: "not_applied", message: RANGE_CHANGED_MESSAGE });
    expect(state.edits).toEqual([]);
  });

  it("refuses when the document changed since the check", async () => {
    const { api, state } = fake();
    state.paragraphs[1]!.text = state.paragraphs[1]!.text.replace("the the", "the");
    expect(await applyReplacement(api, loc(0), "the")).toEqual({ ok: false, outcome: "not_applied", message: CHANGED_MESSAGE });
    expect(state.edits).toEqual([]);
  });

  it("refuses an approximate location: a prefix must never be replaced", async () => {
    const { api, state } = fake();
    const r = await applyReplacement(api, { ...loc(0), exact: false }, "The");
    expect(r).toEqual({ ok: false, outcome: "not_applied", message: APPROXIMATE_APPLY_MESSAGE });
    expect(state.edits).toEqual([]);
  });

  it("refuses to edit inside a Word field such as a citation", async () => {
    const { api, state } = fake({ fieldParagraphs: [1] });
    expect(await applyReplacement(api, loc(0), "the")).toEqual({ ok: false, outcome: "not_applied", message: FIELD_MESSAGE });
    expect(state.edits).toEqual([]);
  });
});

/* The Codex review's R3 reproductions: each host failure on its own side of the edit. */
describe("applying a fix when Word fails (fails closed, says what happened)", () => {
  const ORIGINAL = PARAS[1]!.text;

  it("field enumeration fails: the range is treated as unsafe, nothing is inserted, a manual edit is offered", async () => {
    const { api, state } = fake({ failures: { fields: true } });
    const r = await applyReplacement(api, loc(0), "the");
    expect(r).toEqual({ ok: false, outcome: "not_applied", message: FIELD_UNKNOWN_MESSAGE });
    expect(r.ok ? "" : r.message).toMatch(/by hand/);
    expect(state.edits).toEqual([]);
    expect(state.paragraphs[1]!.text).toBe(ORIGINAL);
    // Tracking was never switched on, so there is nothing to put back.
    expect(state.trackingWrites).toEqual([]);
  });

  it("insertion fails with nothing changed: not applied, and Track Changes is put back", async () => {
    const { api, state } = fake({ failures: { insert: "before" }, trackingMode: "Off" });
    const r = await applyReplacement(api, loc(0), "the");
    expect(r).toEqual({ ok: false, outcome: "not_applied", message: WORD_FAILED_MESSAGE });
    expect(state.paragraphs[1]!.text).toBe(ORIGINAL);
    expect(state.trackingWrites).toEqual(["TrackAll", "Off"]);
    expect(state.trackingMode).toBe("Off");
  });

  it("Word reports an error after the insertion ran: the outcome is unknown, never \"nothing was changed\"", async () => {
    const { api, state } = fake({ failures: { insert: "after" } });
    const r = await applyReplacement(api, loc(0), "the");
    expect(r).toEqual({ ok: false, outcome: "unknown", message: UNKNOWN_MESSAGE });
    expect(UNKNOWN_MESSAGE).toBe("Word reported an error after the edit; check the text before trying again.");
    expect(r.ok ? "" : r.message).not.toMatch(/nothing was changed/i);
    expect(state.edits).toHaveLength(1);
    expect(state.trackingMode).toBe("Off");
  });

  it("selection fails after a good edit: still applied (the selection is not the edit)", async () => {
    const { api, state } = fake({ failures: { select: true } });
    expect(await applyReplacement(api, loc(0), "the")).toEqual({ ok: true, outcome: "applied", tracked: true });
    expect(state.edits).toHaveLength(1);
    expect(state.selection).toBeNull();
    expect(state.trackingMode).toBe("Off");
  });

  it("selection fails when showing a suggestion: refused, with nothing changed", async () => {
    const { api, state } = fake({ failures: { select: true } });
    expect(await selectSpan(api, loc(0))).toEqual({ ok: false, message: WORD_FAILED_MESSAGE });
    expect(state.edits).toEqual([]);
  });

  it("restoring Track Changes fails after the insertion: applied, and said plainly", async () => {
    const { api, state } = fake({ failures: { restoreTracking: true }, trackingMode: "Off" });
    const r = await applyReplacement(api, loc(1), "the");
    expect(r).toEqual({ ok: true, outcome: "restore_failed", tracked: true, message: RESTORE_FAILED_MESSAGE });
    expect(RESTORE_FAILED_MESSAGE).toBe("The change was made, but Track Changes could not be switched back; check Word's Review tab.");
    // The one insertion happened, and the review's bug (reporting it as "nothing was changed") is gone.
    expect(state.edits).toEqual([expect.objectContaining({ before: "the the", text: "the", tracked: true })]);
    expect(state.trackingMode).toBe("TrackAll");
  });

  it("a host that refuses the whole batch after reading: looks again before saying nothing changed", async () => {
    const { api, state } = fake();
    const realRun = api.Word.run.bind(api.Word);
    let calls = 0;
    // The first batch edits the document and then the host throws from Word.run itself.
    api.Word.run = (async (batch: Parameters<typeof realRun>[0]) => {
      calls++;
      if (calls === 1) {
        await realRun(batch);
        throw new Error("RichApi.Error: the host went away");
      }
      return realRun(batch);
    }) as typeof api.Word.run;
    const r = await applyReplacement(api, loc(0), "the");
    expect(r).toEqual({ ok: false, outcome: "unknown", message: UNKNOWN_MESSAGE });
    expect(state.edits).toHaveLength(1);
  });
});

describe("start-up", () => {
  it("reports Word, and whether tracked changes are available", async () => {
    // `Word` does not exist until onReady resolves: start-up must not need it earlier.
    const a = fresh();
    expect(a.target.Word).toBeUndefined();
    expect(await waitForOffice(a.api, 1000, a.wordApi)).toEqual({ status: "word", trackChanges: true });
    const b = fresh({ api14: false });
    expect(await waitForOffice(b.api, 1000, b.wordApi)).toEqual({ status: "word", trackChanges: false });
  });
  it("says when the page is open outside Word, or office.js never loaded", async () => {
    // In a browser office.js loads, never defines `Word`, and says host null.
    const browser = fresh({ host: null });
    expect(await waitForOffice(browser.api, 1000, browser.wordApi)).toEqual({ status: "not_word" });
    expect(await waitForOffice(null)).toEqual({ status: "unavailable" });
    const f = fresh();
    const never = { Office: { ...f.api.Office, onReady: () => new Promise<never>(() => {}) } };
    expect(await waitForOffice(never, 10, f.wordApi)).toEqual({ status: "unavailable" });
  });
  it("is unavailable when Office says Word but the Word API never arrived", async () => {
    const f = fresh();
    expect(await waitForOffice(f.api, 1000, () => null)).toEqual({ status: "unavailable" });
  });
  it("puts back history functions office.js removed", () => {
    const push = () => {};
    const replace = () => {};
    const win = { history: { pushState: null, replaceState: null }, __researchlyHistory: { pushState: push, replaceState: replace } };
    restoreHistory(win as unknown as Window);
    expect(win.history.pushState).toBe(push);
    expect(win.history.replaceState).toBe(replace);
  });
});

describe("where the cursor is", () => {
  it("counts the paragraphs from the start of the body to the selection", async () => {
    const { api } = fake({ cursor: 2 });
    expect(await readSelectionParagraph(api)).toBe(2);
    expect(await readSelectionParagraph(fake({ cursor: 0 }).api)).toBe(0);
    expect(await readSelectionParagraph(fake().api)).toBe(0);
  });

  it("follows a selection made since (clicking a card moved the cursor)", async () => {
    const { api } = fake({ cursor: 0 });
    await selectSpan(api, loc(1));
    expect(await readSelectionParagraph(api)).toBe(1);
  });
});
