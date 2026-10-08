/**
 * The selling point (PLAN.md S4, owner framing 2026-10-08; bounded after
 * the Codex review's "Product claims and evaluation", 8 October 2026).
 * Static copy, below the checker: people come to check a draft first.
 *
 * Every claim here is a row of ARCHITECTURE.md §1.3 and says only what is
 * built: the checks are written rules, the noise is measured as a flag
 * rate (not yet as precision), no cloud or generative model reads the
 * text. Plain English, no superlatives, no numbers.
 */
export function WhyResearchly() {
  return (
    <section className="why-researchly" aria-labelledby="why-heading" data-testid="why-researchly">
      <h2 id="why-heading">Why Researchly</h2>
      <p className="why-problem">
        Feedback on scientific writing usually arrives late, after a draft has gone to a supervisor or a reviewer, and no
        two readers give the same advice. Grammar checkers stop at the sentence; generative tools write the text for you.
        Researchly reads the whole draft like a careful reader, explains each point and leaves every change to you.
      </p>
      <ul className="why-list">
        <li>
          <strong>Same draft, same advice.</strong> With the same settings, the same text gets the same feedback: the
          checks are written rules, not a generative model.
        </li>
        <li>
          <strong>A source for every suggestion.</strong> Each flag says what was noticed, why it matters and where the
          advice comes from, so you can judge it rather than take it on trust.
        </li>
        <li>
          <strong>No cloud or generative AI reads your draft.</strong> The text is processed in memory for one request by
          Researchly&rsquo;s own engine and then dropped. A local mode that sends nothing anywhere is available for the
          Word add-in.
        </li>
        <li>
          <strong>It never writes for you.</strong> There is no drafting, rewriting or paraphrasing, so it fits where
          generative AI is restricted.
        </li>
        <li>
          <strong>Its noise is measured.</strong> How often it flags accepted theses and published papers is tracked as
          a check on false alarms; precision from labelled paragraphs is being added.
        </li>
        <li>
          <strong>Checks across the whole draft.</strong> Figures and tables cited in order, abbreviations defined once,
          numbers in the text found in the table they cite, equations that belong to sentences, and advice that changes
          with the section.
        </li>
      </ul>
      <p className="why-for">
        Researchly is for early-career researchers and for anyone writing in English as a second language. It teaches
        the conventions of research writing while you write, and it encourages you to do the writing yourself.
      </p>
    </section>
  );
}
