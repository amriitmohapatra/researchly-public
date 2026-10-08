import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LEARN_CARDS, type LearnCard } from "@researchly/contract";
import { Lesson, LessonIndex } from "@/components/pages/Lessons";
import { cardById, cardForRule, groupedCards, LEARN_GROUPS, lessonHref } from "@/lib/learn";

/** A synthetic card for the rendering tests. */
const CARD: LearnCard = {
  id: "a-card",
  title: "Say it once",
  group: "Words",
  summary: "Repetition <costs> attention.",
  lesson: "A reader notices a repeated word and wonders whether it means something new.",
  before: "The model was a model of transmission.",
  after: "The model described transmission.",
  habit: "Read each paragraph aloud and listen for the word you hear twice.",
  source: "A named source (Researchly notes)",
  rules: ["W202"],
  moves: [],
};

describe("the Learn cards (S4c)", () => {
  it("groups every card under its group, in the engine's order", () => {
    const groups = groupedCards();
    expect(groups.map((g) => g.group)).toEqual([...LEARN_GROUPS]);
    expect(groups.flatMap((g) => g.cards)).toHaveLength(LEARN_CARDS.length);
    for (const g of groups) for (const c of g.cards) expect(c.group).toBe(g.group);
  });

  it("puts a group the site does not know after the known ones", () => {
    const groups = groupedCards([{ ...CARD, group: "New" }, { ...CARD, id: "b", group: "Words" }]);
    expect(groups.map((g) => g.group)).toEqual(["Words", "New"]);
  });

  it("every card has what its page shows, and an id that is safe in a URL", () => {
    for (const c of LEARN_CARDS) {
      for (const f of ["title", "summary", "lesson", "before", "after", "habit", "source"] as const) expect(c[f].trim()).not.toBe("");
      expect(c.id).toMatch(/^[a-z0-9-]+$/);
      expect(lessonHref(c)).toBe(`/learn/${c.id}`);
    }
    expect(new Set(LEARN_CARDS.map((c) => c.id)).size).toBe(LEARN_CARDS.length);
  });

  it("finds a card by id, and the lesson for a rule (the registry's learn_ref first)", () => {
    const first = LEARN_CARDS[0]!;
    expect(cardById(first.id)).toBe(first);
    expect(cardById("no-such-card")).toBeNull();
    const rid = LEARN_CARDS.find((c) => (c.rules ?? []).length > 0)!.rules![0]!;
    expect(cardForRule(rid, null)).toBe(LEARN_CARDS.find((c) => (c.rules ?? []).includes(rid)));
    expect(cardForRule("ZZ999", first.id)).toBe(first);
    expect(cardForRule("ZZ999", "no-such-card")).toBeNull();
    expect(cardForRule("W202", null, [CARD])).toBe(CARD);
  });

  it("the index links every card to its page, title and summary", () => {
    const html = renderToStaticMarkup(<LessonIndex groups={groupedCards()} />);
    for (const c of LEARN_CARDS) expect(html).toContain(`href="/learn/${c.id}"`);
    const one = renderToStaticMarkup(<LessonIndex groups={[{ group: "Words", cards: [CARD] }]} />);
    expect(one).toContain("<h2");
    expect(one).toContain("Say it once");
    expect(one).toContain("Repetition &lt;costs&gt; attention.");
  });

  it("a lesson reads: title, lesson, Before and After quoted, the habit, the source like a card's, a way back", () => {
    const html = renderToStaticMarkup(<Lesson card={CARD} prev={null} next={{ ...CARD, id: "next", title: "Next one" }} />);
    const order = ["Say it once", CARD.lesson, ">Before<", CARD.before, ">After<", CARD.after, "Check your own draft", CARD.habit, "Source:", CARD.source, "All lessons"];
    let at = -1;
    for (const part of order) {
      const i = html.indexOf(part);
      expect(i, part).toBeGreaterThan(at);
      at = i;
    }
    expect(html.match(/<blockquote/g)).toHaveLength(2);
    expect(html).toContain('<cite>A named source (Researchly notes)</cite>');
    expect(html).toContain('href="/learn/next"');
    expect(html).not.toContain("Previous:");
  });
});
