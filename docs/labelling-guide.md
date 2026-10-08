# Labelling guide: measuring flag precision (S4 exit check)

S4 closes when flag precision on 50 labelled paragraphs is reported in
PLAN.md. This guide says how to label so the number means something.

## What you label

A **flag** is one suggestion card. For each flag you answer one question:

> **Is this flag right, or worth acting on, in this paragraph?**

- **Useful**: the flag points at something real. You would change the text,
  or you would at least want to have been asked. A Convention you choose not
  to follow is still *useful* if the convention is real and correctly
  described: Conventions are norms you may decline, not errors.
- **Wrong**: a false flag. The flagged words do not have the problem the
  card describes (a correct spelling flagged as a typo, a hedge stack that is
  one hedge, passive voice flagged where the doer genuinely does not matter,
  a "missing" figure citation that is there).
- **Unsure**: you cannot tell without more context, or the advice is a
  matter of taste. Unsure flags are counted but left out of precision.

Label the flag, not the paragraph and not the advice in general. A rule you
dislike can still be *useful* on a given sentence.

## Which paragraphs

Fifty paragraphs of **your own writing**, so nothing third-party is
involved:

- spread across sections: about 10 each from Introduction, Methods, Results,
  Discussion, and 10 from abstracts or conclusions;
- spread across drafts: some rough first drafts, some revised text;
- whole paragraphs, checked one at a time with the right section heading
  above them (Researchly's advice depends on the section);
- skip paragraphs with no flags: precision is about the flags shown.

Do not pick paragraphs because they have interesting flags. Take them in
order from a chapter or two and keep the ones that have at least one flag.

## How

1. Open the website's **Label** page (it appears in the menu when you are
   signed in, and also at `/label`).
2. Choose the section, paste one paragraph, check it, and mark each card
   Useful, Wrong or Unsure. Move to the next paragraph.
3. When you have 50, press **Export labels**. The file holds rule ids,
   categories, sections, paragraph numbers and your verdicts. **It holds no
   text**: neither the paragraphs nor the flagged words leave the page.
4. Run the report:

   ```
   python3.10 ml/eval/label_precision.py ~/Downloads/researchly-labels.json
   ```

   It prints precision overall, by category and by rule, each with a 95%
   interval (Wilson), and the rules with the most false flags.
5. Paste the report into PLAN.md under S4's exit check, or send the file to
   Claude to do it.

## Reading the result

- 50 paragraphs give a few hundred flags at most: a rule with five flags has
  a wide interval. Read the intervals, not just the percentages.
- The precision gate for any future learned critic is 0.85 (ARCHITECTURE.md
  ADR-06). The rule-based engine is measured against the same bar.
- A rule with many *wrong* labels is a tuning target: its false flags become
  don't-fire tests (CLAUDE.md #5) before the rule changes.
- This is not the noise floor. Flags per 1,000 words on accepted theses is a
  proxy for fatigue (a flag on published prose can still be valid advice);
  labelled precision is the measured false-flag rate the noise floor stands
  in for (Codex review, "Product claims and evaluation").
