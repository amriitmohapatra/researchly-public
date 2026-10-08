import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LEARN_CARDS } from "@researchly/contract";
import { ChecklistView } from "@/components/ChecklistView";
import { LessonDisclosure } from "@/components/LessonDisclosure";
import { SuggestionCard } from "@/components/SuggestionCard";
import { ViewTabs } from "@/components/ViewTabs";
import { CHECKLIST } from "../../e2e/fixtures";
import { sugg } from "./helpers";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
const noop = () => undefined;

describe("the lesson disclosure", () => {
  const card = LEARN_CARDS.find((c) => c.id === "hedging")!;
  const html = renderToStaticMarkup(<LessonDisclosure learnRef="hedging" />);

  it("is a closed native disclosure called 'The lesson'", () => {
    expect(html.startsWith('<details class="lesson"')).toBe(true);
    expect(html).not.toMatch(/<details[^>]* open/);
    expect(html).toContain("<summary>The lesson</summary>");
  });

  it("holds the card's title, lesson, before and after quoted and labelled, the habit and the source", () => {
    expect(html).toContain(esc(card.title));
    expect(html).toContain(esc(card.lesson));
    expect(html).toMatch(/<figcaption class="lesson-example-label">Before<\/figcaption><blockquote class="lesson-quote"><q>/);
    expect(html).toContain(`<q>${esc(card.before)}</q>`);
    expect(html).toContain(`<q>${esc(card.after)}</q>`);
    expect(html.indexOf(esc(card.before))).toBeLessThan(html.indexOf(esc(card.after)));
    expect(html).toContain(esc(card.habit));
    expect(html).toContain(`<cite>${esc(card.source)}</cite>`);
  });

  it("links to all lessons in a new tab, so the results are never left", () => {
    expect(html).toMatch(/<a href="\/learn" target="_blank" rel="noopener"[^>]*>All lessons<span class="sr-only"> \(opens in a new tab\)<\/span><\/a>/);
  });

  it("renders nothing without a known card", () => {
    for (const ref of [null, undefined, "", "no-such-card"]) expect(renderToStaticMarkup(<LessonDisclosure learnRef={ref} />)).toBe("");
  });
});

describe("the card's lesson and dismissal", () => {
  const s = sugg("x1", 0, 4, "improvement", { learn_ref: "concise-words", text: "word" });

  it("carries the lesson after the full reasoning and before the source, and offers 'Not an issue here' only when the results can dismiss", () => {
    const withDismiss = renderToStaticMarkup(<SuggestionCard suggestion={s} active={false} placeable onShowInText={noop} onDismiss={noop} />);
    const order = ['data-testid="card-reasoning"', 'data-testid="lesson"', 'class="card-source"', 'data-testid="dismiss"'].map((m) => withDismiss.indexOf(m));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(withDismiss).toContain(">Not an issue here</button>");
    const without = renderToStaticMarkup(<SuggestionCard suggestion={s} active={false} placeable onShowInText={noop} />);
    expect(without).not.toContain("Not an issue here");
    expect(without).not.toContain("card-actions");
  });

  it("has no lesson when the engine names none", () => {
    const html = renderToStaticMarkup(<SuggestionCard suggestion={{ ...s, learn_ref: null }} active={false} placeable onShowInText={noop} />);
    expect(html).not.toContain('data-testid="lesson"');
  });
});

describe("the results tabs", () => {
  it("offer three views by default and the checklist only when asked", () => {
    const three = renderToStaticMarkup(<ViewTabs view="suggestions" onChange={noop} idBase="t" />);
    expect([...three.matchAll(/data-testid="view-([a-z]+)"/g)].map((m) => m[1])).toEqual(["suggestions", "brief", "narrative"]);
    const four = renderToStaticMarkup(<ViewTabs view="checklist" onChange={noop} idBase="t" views={["suggestions", "brief", "narrative", "checklist"]} />);
    expect([...four.matchAll(/data-testid="view-([a-z]+)"/g)].map((m) => m[1])).toEqual(["suggestions", "brief", "narrative", "checklist"]);
    expect(four).toMatch(/aria-selected="true"[^>]*data-testid="view-checklist"/);
  });
});

describe("the checklist view", () => {
  const screen = renderToStaticMarkup(<ChecklistView report={CHECKLIST} notApplicable={new Set()} onToggle={noop} />);

  it("reads as a document: the note, every item in order with topic, question and status in words, then the source and the scope line", () => {
    expect(screen).toContain(esc(CHECKLIST.note));
    expect([...screen.matchAll(/data-item="([a-z-]+)"/g)].map((m) => m[1])).toEqual(CHECKLIST.items.map((i) => i.id));
    for (const it of CHECKLIST.items) {
      expect(screen).toContain(`>${esc(it.topic)}</h3>`);
      expect(screen).toContain(esc(it.question));
    }
    expect([...screen.matchAll(/<span class="checklist-status-word">([^<]+)<\/span>/g)].map((m) => m[1])).toEqual([
      "reported",
      "needs your check",
      "needs your check",
    ]);
    // Reported: the writer's own sentence, quoted. Needs your check: the reason in everyday words.
    expect(screen).toContain(`<q>${esc(CHECKLIST.items[0]!.evidence!)}</q>`);
    expect(screen).toContain(`<p class="checklist-plain">${esc(CHECKLIST.items[1]!.plain)}</p>`);
    expect(screen.indexOf("checklist-source")).toBeLessThan(screen.indexOf('data-testid="checklist-scope">This checks reporting only, never the science.'));
    expect(screen).toContain(`<cite>${esc(CHECKLIST.source)}</cite>`);
    expect(screen).not.toMatch(/<meter|<progress|\d+ ?%|score/i);
  });

  it("offers a session-only 'Not applicable' per item on screen, and says it in place of the status", () => {
    expect(screen.match(/data-testid="checklist-na"/g)).toHaveLength(CHECKLIST.items.length);
    expect(screen).toMatch(/aria-pressed="false"/);
    const na = renderToStaticMarkup(<ChecklistView report={CHECKLIST} notApplicable={new Set(["horizon"])} onToggle={noop} />);
    expect(na).toContain("not applicable (your call)");
    expect(na).toMatch(/aria-pressed="true"/);
    expect(na).not.toContain(esc(CHECKLIST.items[1]!.plain));
  });

  it("on paper has no controls and keeps the writer's 'Not applicable'", () => {
    const paper = renderToStaticMarkup(<ChecklistView report={CHECKLIST} notApplicable={new Set(["uncertainty"])} variant="print" />);
    expect(paper).not.toContain("<button");
    expect(paper).toContain("not applicable (your call)");
    expect(paper).toContain('class="checklist checklist-print"');
  });
});
