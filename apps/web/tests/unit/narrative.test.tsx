import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { NarrativeMap as Map, NarrativeMove } from "@researchly/contract";
import { NarrativeMap, STATUS_WORD } from "@/components/NarrativeMap";

/** A move with everything the engine sends; synthetic throughout. */
function move(id: string, label: string, status: NarrativeMove["status"], extra: Partial<NarrativeMove> = {}): NarrativeMove {
  return {
    id,
    label,
    status,
    question: `Does the section say ${label.toLowerCase()}?`,
    plain: `The lesson for ${label.toLowerCase()}, in everyday words.`,
    frame: `“[A frame for ${label.toLowerCase()}].”`,
    source: "A named source (Researchly notes)",
    evidence: status === "present" ? `The sentence that carries ${label.toLowerCase()} <and> more.` : null,
    note: "",
    ...extra,
  };
}

/** Five sections; one move missing (Introduction), one out of order (Discussion). */
const map: Map = {
  note: "2 expected moves are missing; each one below has a question and a frame to fill in.",
  profile: "manuscript",
  source: "J. M. Swales (1990), Genre Analysis; a named source (Researchly notes)",
  unmapped: ["Study area", "Ethics"],
  sections: [
    {
      section: "abstract",
      label: "Abstract",
      sentences: 3,
      words: 60,
      present: 2,
      expected: 2,
      moves: [move("ab.known", "What is known", "present"), move("ab.found", "What was found", "present")],
    },
    {
      section: "introduction",
      label: "Introduction",
      sentences: 4,
      words: 90,
      present: 2,
      expected: 3,
      moves: [
        move("in.why", "Why it matters", "present"),
        move("in.gap", "What is missing", "missing"),
        move("in.aim", "What you set out to do", "present"),
      ],
    },
    { section: "methods", label: "Methods", sentences: 5, words: 120, present: 1, expected: 1, moves: [move("me.data", "The data", "present")] },
    { section: "results", label: "Results", sentences: 2, words: 40, present: 1, expected: 1, moves: [move("re.found", "What was found", "present")] },
    {
      section: "discussion",
      label: "Discussion",
      sentences: 6,
      words: 150,
      present: 2,
      expected: 2,
      moves: [
        move("di.meaning", "What it means", "out_of_order", {
          note: "Appears after what should change.",
          evidence: "The sentence that carries what it means <and> more.",
        }),
        move("di.change", "What should change", "present", { evidence: " Practice should change.  " }),
      ],
    },
  ],
  missing_links: [
    {
      section: "discussion",
      label: "Discussion",
      code: "claim_without_warrant",
      message: "A claim in the Discussion has no warrant: the reader is not told why the evidence supports it.",
      source: "M. Wallace & A. Wray (2016); S. Toulmin (1958)",
    },
  ],
  hedging: [
    { section: "introduction", label: "Introduction", words: 90, hedges_per_100w: 2.22, boosters_per_100w: 0, reading: "hedged" },
    { section: "discussion", label: "Discussion", words: 150, hedges_per_100w: 9.33, boosters_per_100w: 1.33, reading: "heavily hedged" },
  ],
};

const render = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el);
const texts = (html: string, re: RegExp) => [...html.matchAll(re)].map((m) => m[1]);
const section = (html: string, id: string) => {
  const start = html.indexOf(`data-section="${id}"`);
  const next = html.indexOf('data-testid="narrative-section"', start + 1);
  return html.slice(start, next < 0 ? html.indexOf('data-testid="narrative-links"') : next);
};

describe("the narrative map", () => {
  const html = render(<NarrativeMap state={{ kind: "ready", narrative: map }} />);

  it("opens with the engine's note, then one strip per section in order, each saying how many moves are present", () => {
    expect(html.indexOf("2 expected moves are missing")).toBeLessThan(html.indexOf('data-testid="narrative-section"'));
    expect(texts(html, /data-testid="narrative-section" data-section="([a-z]+)"/g)).toEqual([
      "abstract",
      "introduction",
      "methods",
      "results",
      "discussion",
    ]);
    expect(section(html, "introduction")).toContain("2 of 3 moves present");
    expect(section(html, "methods")).toContain("1 of 1 move present");
  });

  it("marks every move by its status word, never by colour alone: present cells carry no word, missing and out-of-order ones do", () => {
    const intro = section(html, "introduction");
    expect(texts(intro, /data-testid="narrative-move" data-move="([a-z.]+)"/g)).toEqual(["in.why", "in.gap", "in.aim"]);
    expect(intro).toContain('data-move="in.gap" data-status="missing"');
    expect(intro).toContain('<span class="nmap-cell-status">missing</span>');
    const disc = section(html, "discussion");
    expect(disc).toContain('data-move="di.meaning" data-status="out_of_order"');
    expect(disc).toContain('<span class="nmap-cell-status">out of order</span>');
    expect(disc).toContain("nmap-cell-out-of-order");
    // On screen a present cell is the filled dot and the label alone.
    expect(intro).toMatch(/data-move="in\.why" data-status="present"><span class="nmap-dot" aria-hidden="true"><\/span><span class="nmap-cell-label">Why it matters<\/span><\/li>/);
    expect(STATUS_WORD).toEqual({ present: "present", missing: "missing", out_of_order: "out of order" });
  });

  it("opens a missing move to its question, the lesson, the frame with its caption, and the source", () => {
    const intro = section(html, "introduction");
    const detail = intro.slice(intro.indexOf('data-testid="narrative-detail" data-move="in.gap"'));
    expect(detail).toContain('<p class="nmap-question">Does the section say what is missing?</p>');
    expect(detail).toContain('<p class="nmap-plain">The lesson for what is missing, in everyday words.</p>');
    expect(detail).toContain('<blockquote class="nmap-frame-text">“[A frame for what is missing].”</blockquote>');
    expect(detail).toContain("A frame to fill in; the words are yours.");
    expect(detail).toContain("Source:");
    expect(detail).toContain("<cite>A named source (Researchly notes)</cite>");
    // A present move is not opened: no question or frame for it.
    expect(intro).not.toContain("Does the section say why it matters?");
    expect(intro).not.toContain("[A frame for why it matters]");
  });

  it("opens an out-of-order move with its note, and still quotes the sentence it rests on", () => {
    const disc = section(html, "discussion");
    const detail = disc.slice(disc.indexOf('data-testid="narrative-detail" data-move="di.meaning"'), disc.indexOf('data-testid="narrative-present"'));
    expect(detail).toContain('<span class="nmap-detail-status">out of order</span>');
    expect(detail).toContain("Appears after what should change.");
    expect(detail).toContain("Does the section say what it means?");
    expect(detail).toContain("<q>The sentence that carries what it means &lt;and&gt; more.</q>");
  });

  it("keeps a present move's sentence behind a disclosure, quoted, escaped and trimmed", () => {
    const disc = section(html, "discussion");
    const present = disc.slice(disc.indexOf('data-testid="narrative-present" data-move="di.change"'));
    expect(present).toContain("<details");
    expect(present).toContain("Show the sentence");
    expect(present).toContain("<q>Practice should change.</q>");
    expect(present).not.toContain("<details open");
    // Every present move with a sentence has one (seven across the five sections); the out-of-order move's quote makes eight; none is loose in the prose.
    expect(html.match(/data-testid="narrative-present"/g)).toHaveLength(7);
    expect(html.match(/<q>/g)).toHaveLength(8);
  });

  it("lists the argument's missing links with their section, message and source, then the hedging table with every value in text", () => {
    const links = html.slice(html.indexOf('data-testid="narrative-links"'), html.indexOf('data-testid="narrative-hedging"'));
    expect(links).toContain("Argument: missing links");
    expect(links).toContain('data-code="claim_without_warrant"');
    expect(links).toContain('<span class="nmap-link-section">Discussion</span>');
    expect(links).toContain("has no warrant");
    expect(links).toContain("<cite>M. Wallace &amp; A. Wray (2016); S. Toulmin (1958)</cite>");
    const hedging = html.slice(html.indexOf('data-testid="narrative-hedging"'));
    expect(hedging).toContain("Hedging across the document");
    expect(texts(hedging, /data-section="([a-z]+)"/g)).toEqual(["introduction", "discussion"]);
    expect(hedging).toContain('<th scope="row">Introduction</th><td class="nmap-num">2.2</td><td class="nmap-num">0.0</td><td>hedged</td>');
    expect(hedging).toContain('<th scope="row">Discussion</th><td class="nmap-num">9.3</td><td class="nmap-num">1.3</td><td>heavily hedged</td>');
    expect(hedging).toContain("not a score");
  });

  it("names the headings with no expected moves, as given, and ends with the source", () => {
    expect(html).toContain("Headings with no expected moves: Study area, Ethics");
    expect(html.lastIndexOf("<cite>J. M. Swales (1990), Genre Analysis; a named source (Researchly notes)</cite>")).toBeGreaterThan(
      html.indexOf('data-testid="narrative-hedging"'),
    );
  });

  it("carries no score, meter or percentage, and no section numbers of the guide", () => {
    expect(html).not.toMatch(/<meter|<progress|\d+ ?%|\d+ ?\/ ?10|§/);
  });

  it("without links or unmapped headings says so, and leaves the lines out", () => {
    const h = render(<NarrativeMap state={{ kind: "ready", narrative: { ...map, missing_links: [], unmapped: [], hedging: [] } }} />);
    expect(h).toContain("No missing links");
    expect(h).not.toContain("Headings with no expected moves");
    expect(h).not.toContain('data-testid="narrative-hedging"');
  });

  it("with no sections (no headings) shows the note and the rest, and no strip", () => {
    const h = render(
      <NarrativeMap
        state={{
          kind: "ready",
          narrative: { ...map, sections: [], unmapped: ["unknown"], note: "No section headings were found, so there is no map to draw." },
        }}
      />,
    );
    expect(h).toContain("No section headings were found");
    expect(h).not.toContain('data-testid="narrative-section"');
    expect(h).toContain("Headings with no expected moves: unknown");
  });

  it("on paper the strip is text rows with every status word, and every sentence is open", () => {
    const h = render(<NarrativeMap state={{ kind: "ready", narrative: map }} variant="print" />);
    expect(h).toContain('class="nmap nmap-print"');
    expect(h).not.toContain("<details");
    expect(h).not.toContain("Show the sentence");
    expect(h.match(/<span class="nmap-cell-status">present<\/span>/g)).toHaveLength(7);
    expect(h).toContain("<q>Practice should change.</q>");
    expect(h).toContain("“[A frame for what is missing].”");
  });

  it("in Draft says the map needs Revise, with a switch only where the surface has one", () => {
    const plain = render(<NarrativeMap state={{ kind: "needs_revise" }} />);
    expect(plain).toContain("needs Revise mode");
    expect(plain).not.toContain("<button");
    const withSwitch = render(<NarrativeMap state={{ kind: "needs_revise" }} onSwitchToRevise={() => undefined} />);
    expect(withSwitch).toContain("Switch to Revise");
    expect(withSwitch).not.toContain("narrative-section");
  });

  it("says when an engine returned no map", () => {
    const h = render(<NarrativeMap state={{ kind: "missing" }} />);
    expect(h).toContain("did not return a narrative map");
    expect(h).not.toContain("narrative-section");
  });
});

describe("the narrative map's lessons and link sentences (S4)", () => {
  const withLessons: Map = {
    ...map,
    sections: map.sections.map((s) => ({ ...s, moves: s.moves.map((m) => ({ ...m, learn_ref: "introduction" })) })),
    missing_links: [
      { ...map.missing_links![0]!, learn_ref: "warranting", evidence: ["A claim <with> no warrant.", "  "] },
      { section: "results", label: "Results", code: "claim_without_grounds", message: "A claim with nothing under it.", source: "S. Toulmin (1958)", learn_ref: null, evidence: [] },
    ],
  };
  const html = render(<NarrativeMap state={{ kind: "ready", narrative: withLessons }} />);

  it("opens a missing or out-of-order move's lesson from a closed disclosure; a present move has none", () => {
    expect(html.match(/data-testid="lesson" data-lesson="introduction"/g)).toHaveLength(2);
    const intro = section(html, "introduction");
    expect(intro.indexOf('data-lesson="introduction"')).toBeGreaterThan(intro.indexOf('data-move="in.gap"'));
    expect(section(html, "methods")).not.toContain('data-testid="lesson"');
  });

  it("gives a link its lesson and its sentences behind 'Show the sentence', and nothing when it has neither", () => {
    const links = html.slice(html.indexOf('data-testid="narrative-links"'));
    expect(links).toContain('data-lesson="warranting"');
    expect(links).toContain('<span class="nmap-sentence-link">Show the sentence</span>');
    expect(links).toContain("<q>A claim &lt;with&gt; no warrant.</q>");
    const second = links.slice(links.indexOf('data-code="claim_without_grounds"'));
    expect(second).not.toContain('data-testid="lesson"');
    expect(second).not.toContain("narrative-link-evidence");
  });

  it("on paper leaves the lessons out and the sentences open", () => {
    const paper = render(<NarrativeMap state={{ kind: "ready", narrative: withLessons }} variant="print" />);
    expect(paper).not.toContain('data-testid="lesson"');
    expect(paper).not.toContain("<details");
    expect(paper).toContain("<q>A claim &lt;with&gt; no warrant.</q>");
  });
});
