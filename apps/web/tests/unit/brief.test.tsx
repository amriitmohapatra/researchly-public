import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReviewReport } from "@researchly/contract";
import { ReviewBrief } from "@/components/ReviewBrief";

/** A brief with five questions, synthetic throughout. */
const review: ReviewReport = {
  source: "A named source; Amriit's learnings from scientific-writing training (Researchly notes)",
  disclaimer: "This brief points to what a critical reader would ask. It does not establish whether the science is sound.",
  sections: ["introduction", "discussion"],
  words: 120,
  questions: [
    {
      id: "A",
      status: "yours",
      question: "Why am I reading this?",
      verdict: "Yours to answer: what do you need from this document?",
      points: ["The brief below reads it as a sceptical reader would."],
      evidence: [],
    },
    { id: "B", status: "detected", question: "What are the authors trying to achieve?", verdict: "An aim is stated.", points: [], evidence: ["We set out to test the model."] },
    { id: "C", status: "not_assessed", question: "What are they claiming?", verdict: "No unhedged causal claims found.", points: [], evidence: [] },
    {
      id: "D",
      status: "not_detected",
      question: "How convincing are the claims?",
      verdict: "1 thing weakens the claims; see the points.",
      points: ["No limitations section: the reviewer will supply the rebuttal instead.", " "],
      evidence: ["  ", "The result held in every run <and> in the pilot."],
    },
    { id: "E", status: "not_applicable", question: "What use can be made of this?", verdict: "The significance is stated.", points: [], evidence: ["This changes how teams should plan."] },
  ],
  top_rules: [
    { id: "W202", short: "Wordy phrase", count: 3 },
    { id: "G106", short: "Long sentence", count: 1 },
  ],
};

const render = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el);
const texts = (html: string, re: RegExp) => [...html.matchAll(re)].map((m) => m[1]);

describe("the reviewer's brief", () => {
  const html = render(<ReviewBrief state={{ kind: "ready", review }} />);

  it("renders the five questions in order, each with its letter, question and verdict", () => {
    expect(texts(html, /data-question="([A-E])"/g)).toEqual(["A", "B", "C", "D", "E"]);
    const headings = texts(html, /<h3 class="brief-q-title">(.*?)<\/h3>/g);
    expect(headings).toHaveLength(5);
    expect(headings[0]).toContain("Why am I reading this?");
    expect(headings[4]).toContain("What use can be made of this?");
    const verdicts = texts(html, /<p class="brief-verdict">(.*?)<\/p>/g);
    expect(verdicts).toEqual(review.questions.map((q) => q.verdict));
  });

  it("renders question A as the engine gives it: the writer's to answer", () => {
    expect(html).toContain("Yours to answer: what do you need from this document?");
  });

  it("lists the points, quotes the evidence as the writer's own sentences (escaped), and skips blanks", () => {
    expect(html).toContain("<li>No limitations section: the reviewer will supply the rebuttal instead.</li>");
    expect(html).not.toContain("<li> </li>");
    const quotes = texts(html, /<q>(.*?)<\/q>/g);
    expect(quotes).toEqual([
      "We set out to test the model.",
      "The result held in every run &lt;and&gt; in the pilot.",
      "This changes how teams should plan.",
    ]);
    // Every quote sits in an evidence list, never loose in the prose.
    expect(html.match(/class="brief-evidence"/g)).toHaveLength(3);
  });

  it("ends with the most frequent checks in words and the source as a reference", () => {
    expect(html).toContain("Most frequent checks");
    expect(html).toContain('<span>Wordy phrase</span> <span class="brief-rule-count">3 times</span>');
    expect(html).toContain('<span>Long sentence</span> <span class="brief-rule-count">once</span>');
    expect(html).toContain(`<cite>${review.source.replace(/'/g, "&#x27;")}</cite>`);
    expect(html).toContain("Source:");
  });

  it("carries no score, meter or percentage, and says so", () => {
    expect(html).not.toMatch(/<meter|<progress|\d+ ?%|\d+ ?\/ ?10/);
    expect(html).toContain("Not a score.");
  });

  it("without the frequent checks the section is left out", () => {
    const h = render(<ReviewBrief state={{ kind: "ready", review: { ...review, top_rules: [] } }} />);
    expect(h).not.toContain("Most frequent checks");
    expect(h).toContain("Source:");
  });

  it("in Draft says the brief needs Revise, with a switch only where the surface has one", () => {
    const plain = render(<ReviewBrief state={{ kind: "needs_revise" }} />);
    expect(plain).toContain("needs Revise mode");
    expect(plain).not.toContain("<button");
    const withSwitch = render(<ReviewBrief state={{ kind: "needs_revise" }} onSwitchToRevise={() => undefined} />);
    expect(withSwitch).toContain("Switch to Revise");
    expect(withSwitch).not.toContain("brief-question");
  });

  it("says when an engine returned no brief", () => {
    const h = render(<ReviewBrief state={{ kind: "missing" }} />);
    expect(h).toContain("did not return a brief");
    expect(h).not.toContain("brief-question");
  });
});

describe("the brief's statuses and disclaimer (Codex review R4)", () => {
  const html = render(<ReviewBrief state={{ kind: "ready", review }} />);
  const words = (h: string) => [...h.matchAll(/data-question="([A-E])"[\s\S]*?<\/h3>/g)].map((m) => /data-testid="brief-status" data-status="[a-z_]+">([^<]+)</.exec(m[0])?.[1] ?? "");

  it("says each answer's status as a small word after the question, and nothing for the writer's own question A", () => {
    expect(words(html)).toEqual(["", "detected", "not assessed", "not detected", "not applicable"]);
    // Screen readers hear it in brackets after the question.
    expect(html).toMatch(/What are the authors trying to achieve\?(<!-- -->)? <span class="sr-only">\(<\/span><span class="brief-q-status"/);
  });

  it("never colours by status: one class for every status word", () => {
    expect([...html.matchAll(/<span class="([^"]+)" data-testid="brief-status"/g)].map((m) => m[1])).toEqual(Array(4).fill("brief-q-status"));
  });

  it("an unknown status (a newer engine) or none (an older one) shows no word", () => {
    const odd = {
      ...review,
      questions: review.questions.map((q, i) => (i === 1 ? { ...q, status: "guessed" as never } : i === 2 ? ({ ...q, status: undefined } as never) : q)),
    };
    expect(words(render(<ReviewBrief state={{ kind: "ready", review: odd }} />)).slice(0, 3)).toEqual(["", "", ""]);
  });

  it("closes with the engine's disclaimer, after the frequent checks and before the source", () => {
    const at = (m: string) => html.indexOf(m);
    expect(html).toContain(`<p class="brief-disclaimer" data-testid="brief-disclaimer">${review.disclaimer}</p>`);
    expect(at("brief-rules")).toBeLessThan(at("brief-disclaimer"));
    expect(at("brief-disclaimer")).toBeLessThan(at("brief-source"));
    const none = render(<ReviewBrief state={{ kind: "ready", review: { ...review, disclaimer: "  " } }} />);
    expect(none).not.toContain("brief-disclaimer");
  });
});
