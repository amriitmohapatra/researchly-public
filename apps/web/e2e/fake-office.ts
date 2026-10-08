/**
 * A fake Office.js for tests: the slice of the Word API the taskpane uses
 * (lib/word/office.ts), over an in-memory document.
 *
 * One implementation serves both suites:
 * - e2e: `fakeOfficeScript()` is served in place of Microsoft's office.js by
 *   page.route, so the page loads it exactly as it loads the real one (and
 *   the route's CSP must allow it);
 * - unit: `installFakeOffice({}, config)` builds the globals in Node.
 *
 * `installFakeOffice` must stay self-contained (no imports, no outer
 * variables): it is sent to the browser as its own source text.
 *
 * Faithful where it matters:
 * - changes are queued and applied at `context.sync()`;
 * - setting `changeTrackingMode` without WordApi 1.4 does not throw, it
 *   fails the whole batch at sync and nothing in it is applied (the bug that
 *   once silently killed every Apply in the old add-in);
 * - `search` finds non-overlapping matches, left to right, like Word.
 */

export interface FakeParagraph {
  text: string;
  style?: string;
  styleBuiltIn?: string;
  tableNestingLevel?: number;
}

export interface FakeWordConfig {
  paragraphs: FakeParagraph[];
  /** Office.onReady's host; null = opened outside Office. Default "Word". */
  host?: string | null;
  /** WordApi 1.4 (tracked changes, fields). Default true. */
  api14?: boolean;
  /** The writer's Track Changes setting before any apply. Default "Off". */
  trackingMode?: string;
  /** Paragraph indexes whose ranges sit inside a Word field (a citation). */
  fieldParagraphs?: number[];
  /** Mimic office.js removing history.pushState/replaceState. */
  nullHistory?: boolean;
  /** Where the cursor is when the pane opens: a paragraph index (default 0). */
  cursor?: number;
  /**
   * Host failures to reproduce (Codex review R3), each at `context.sync()`
   * like a real Word error:
   * - `fields`: loading a range's fields fails;
   * - `insert`: "before" fails the insertion with nothing changed, "after"
   *   makes the change and then reports an error (a batch that partly ran);
   * - `select`: selecting a range fails;
   * - `restoreTracking`: switching Track Changes back off (any mode other
   *   than TrackAll) fails.
   */
  failures?: { fields?: boolean; insert?: "before" | "after"; select?: boolean; restoreTracking?: boolean };
}

export interface FakeEdit {
  paragraph: number;
  start: number;
  end: number;
  before: string;
  text: string;
  tracked: boolean;
}

export interface FakeWordState {
  paragraphs: FakeParagraph[];
  selection: { paragraph: number; start: number; end: number; text: string } | null;
  trackingMode: string;
  edits: FakeEdit[];
  failedBatches: number;
  /** Every changeTrackingMode assignment, in order. */
  trackingWrites: string[];
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function installFakeOffice(target: any, config: FakeWordConfig): FakeWordState {
  const api14 = config.api14 !== false;
  const failures = config.failures ?? {};
  const state: FakeWordState = {
    paragraphs: config.paragraphs.map((p) => ({ ...p })),
    selection: null,
    trackingMode: config.trackingMode ?? "Off",
    edits: [],
    failedBatches: 0,
    trackingWrites: [],
  };
  target.__fakeWord = state;
  if (config.nullHistory && target.history) {
    target.history.pushState = null;
    target.history.replaceState = null;
  }

  function versionAtMost(v: string | undefined, max: string): boolean {
    const a = (v ?? "1.1").split(".").map(Number);
    const b = max.split(".").map(Number);
    for (let i = 0; i < 2; i++) {
      if ((a[i] ?? 0) !== (b[i] ?? 0)) return (a[i] ?? 0) < (b[i] ?? 0);
    }
    return true;
  }

  function run(batch: (ctx: any) => Promise<any>) {
    let ops: (() => void)[] = [];
    let poisoned = false;

    // A range inside one paragraph; `endPi` > pi only for a range made by expandTo.
    function makeRange(pi: number, start: number, end: number, endPi: number = pi) {
      const r: any = {
        pi,
        start,
        end,
        endPi,
        text: state.paragraphs[pi]!.text.slice(start, end),
        load() {
          r.text = state.paragraphs[r.pi]!.text.slice(r.start, r.end);
        },
        getRange(where?: string) {
          if (where === "End") return makeRange(r.endPi, r.end, r.end);
          if (where === "Start") return makeRange(r.pi, r.start, r.start);
          return makeRange(r.pi, r.start, r.end, r.endPi);
        },
        expandTo(other: any) {
          const first = other.pi < r.pi || (other.pi === r.pi && other.start < r.start) ? other : r;
          const last = other.endPi > r.endPi || (other.endPi === r.endPi && other.end > r.end) ? other : r;
          return makeRange(first.pi, first.start, last.end, last.endPi);
        },
        get paragraphs() {
          const items: any[] = [];
          for (let i = r.pi; i <= r.endPi; i++) items.push(makeParagraph(i));
          return { items, load() {} };
        },
        select() {
          ops.push(() => {
            if (failures.select) throw new Error("GeneralException: the selection could not be made");
            state.selection = { paragraph: r.pi, start: r.start, end: r.end, text: state.paragraphs[r.pi]!.text.slice(r.start, r.end) };
          });
        },
        insertText(text: string, where: string) {
          if (where !== "Replace") throw new Error(`fake office: unsupported insert location ${where}`);
          ops.push(() => {
            if (failures.insert === "before") throw new Error("GeneralException: the text could not be inserted");
            const p = state.paragraphs[r.pi]!;
            const before = p.text.slice(r.start, r.end);
            p.text = p.text.slice(0, r.start) + text + p.text.slice(r.end);
            state.edits.push({ paragraph: r.pi, start: r.start, end: r.end, before, text, tracked: state.trackingMode === "TrackAll" });
            r.end = r.start + text.length;
            r.text = text;
            if (failures.insert === "after") throw new Error("GeneralException: an error after the insertion");
          });
          return r;
        },
      };
      if (api14) {
        const inField = (config.fieldParagraphs ?? []).includes(pi);
        r.fields = {
          items: inField ? [{ code: "ADDIN ZOTERO_ITEM" }] : [],
          load() {
            if (failures.fields) {
              ops.push(() => {
                throw new Error("GeneralException: the fields could not be read");
              });
            }
          },
        };
      }
      return r;
    }

    function makeParagraph(pi: number) {
      const p: FakeParagraph = state.paragraphs[pi]!;
      return {
        text: p.text,
        style: p.style ?? "Normal",
        styleBuiltIn: p.styleBuiltIn ?? "Other",
        tableNestingLevel: p.tableNestingLevel ?? 0,
        search(needle: string, options: { matchCase?: boolean }) {
          const hay = options?.matchCase ? p.text : p.text.toLowerCase();
          const n = options?.matchCase ? needle : needle.toLowerCase();
          const items: any[] = [];
          if (n) for (let i = hay.indexOf(n); i >= 0; i = hay.indexOf(n, i + n.length)) items.push(makeRange(pi, i, i + n.length));
          return { items, load() {} };
        },
      };
    }

    const paragraphs = {
      items: state.paragraphs.map((_p, i) => makeParagraph(i)),
      load() {
        paragraphs.items = state.paragraphs.map((_p, i) => makeParagraph(i));
      },
    };

    const document: any = {
      body: {
        paragraphs,
        getRange(where?: string) {
          const last = state.paragraphs.length - 1;
          if (where === "Start") return makeRange(0, 0, 0);
          if (where === "End") return makeRange(last, state.paragraphs[last]!.text.length, state.paragraphs[last]!.text.length);
          return makeRange(0, 0, state.paragraphs[last]!.text.length, last);
        },
      },
      load() {},
      getSelection() {
        const sel = state.selection;
        if (sel) return makeRange(sel.paragraph, sel.start, sel.end);
        const pi = Math.min(Math.max(config.cursor ?? 0, 0), state.paragraphs.length - 1);
        return makeRange(pi, 0, 0);
      },
    };
    Object.defineProperty(document, "changeTrackingMode", {
      get: () => state.trackingMode,
      set: (mode: string) => {
        state.trackingWrites.push(mode);
        if (!api14) {
          poisoned = true; // no error now: the batch fails at sync
          return;
        }
        ops.push(() => {
          if (failures.restoreTracking && mode !== "TrackAll") throw new Error("GeneralException: Track Changes could not be set");
          state.trackingMode = mode;
        });
      },
    });

    const ctx = {
      document,
      async sync() {
        const pending = ops;
        ops = [];
        if (poisoned) {
          poisoned = false;
          state.failedBatches++;
          throw new Error("GeneralException: the requested operation is not supported in this Word version");
        }
        for (const op of pending) op();
      },
    };
    return Promise.resolve().then(() => batch(ctx));
  }

  const host = config.host === undefined ? "Word" : config.host;
  target.Office = {
    HostType: { Word: "Word" },
    onReady(cb?: (info: { host: string | null; platform: string | null }) => void) {
      // Like office.js: the host's scripts (and so `Word`) arrive
      // asynchronously, and only inside Word, before onReady resolves.
      return new Promise((resolve) => setTimeout(resolve, 20)).then(() => {
        if (host === "Word") target.Word = wordNamespace;
        const info = { host, platform: host ? "PC" : null };
        if (cb) cb(info);
        return info;
      });
    },
    context: {
      requirements: {
        isSetSupported(name: string, version?: string) {
          if (name !== "WordApi") return false;
          return versionAtMost(version, api14 ? "1.4" : "1.3");
        },
      },
    },
  };
  const wordNamespace = {
    run,
    InsertLocation: { replace: "Replace" },
    ChangeTrackingMode: { off: "Off", trackAll: "TrackAll", trackMineOnly: "TrackMineOnly" },
  };
  // For unit tests that act after start-up: Word as it is once ready.
  target.__fakeWordNamespace = wordNamespace;
  return state;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** The fake as an office.js response body: it reads its config from `window.__fakeWordConfig`. */
export function fakeOfficeScript(): string {
  return `(${installFakeOffice.toString()})(window, window.__fakeWordConfig || { paragraphs: [] });`;
}
