"""Learn cards (S4): the lesson behind every suggestion.

ARCHITECTURE.md: "Every suggestion carries `why`, a named `source` and a
`learn_ref`", and §1.3's promise that Researchly *teaches*. A card is a
short lesson in everyday words, one synthetic before-and-after pair, a
habit for checking your own draft, and the sources it rests on. Several
related rules share a card (every wordy-phrase rule leads to "Say it in
fewer words"), and the narrative map's moves point to the card for their
section.

Everything here is Researchly's own wording. The examples are invented
(the districts are the demo manuscript's fictional ones), the lessons
paraphrase the owner's guide and the named works, and nothing is quoted
from the course material (D7). User-visible text follows the same rule as
the rules' explanations: no section numbers, course codes or names of
people except on the Source line (`tests/test_learn.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import sources


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    group: str
    summary: str          # one line, shown under the title in a list
    lesson: str           # the principle, in everyday words
    before: str           # an invented example of the problem
    after: str            # the same example, revised
    habit: str            # how to check your own draft
    source: str           # code(s) for sources.cite
    rules: tuple = ()
    moves: tuple = field(default_factory=tuple)

    @property
    def citation(self) -> str:
        return sources.cite(self.source)

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "group": self.group,
                "summary": self.summary, "lesson": self.lesson,
                "before": self.before, "after": self.after,
                "habit": self.habit, "source": self.citation,
                "rules": list(self.rules), "moves": list(self.moves)}


GROUPS = ("Sentences", "Words", "Claims and evidence",
          "Figures, tables and numbers", "Structure and argument",
          "Mechanics")

_CARDS = (
    # --- Sentences ------------------------------------------------------------------
    Card("subject-and-verb", "Keep the subject close to its verb", "Sentences",
         "Readers wait for the verb; a long interruption loses them.",
         "Readers hold the subject in mind until the verb arrives and tells "
         "them what it did. A long interruption between the two (a list, a "
         "clause, a string of citations) makes them wait, and many lose the "
         "thread. Move the interruption before the subject or after the verb.",
         "The reproduction number, which we estimated for each district from "
         "weekly counts in the national register with a renewal model and a "
         "seven-day generation interval, fell below one in June.",
         "The reproduction number fell below one in June. We estimated it for "
         "each district from weekly counts in the national register, with a "
         "renewal model and a seven-day generation interval.",
         "Underline the subject and the verb of each long sentence. If more "
         "than a line separates them, move what sits between.",
         "§5.2.1", rules=("G101",)),
    Card("actions-in-verbs", "Put the action in the verb", "Sentences",
         "Actions hidden in nouns make sentences long and weak.",
         "Scientific prose often hides its actions in nouns: 'performed an "
         "estimation of', 'carried out an analysis of'. The sentence grows, "
         "the verb weakens, and the reader has to unpack it. When a noun "
         "ending in -tion, -ment or -ance hides what someone did, try the "
         "verb instead.",
         "An estimation of transmission was performed through the "
         "application of a renewal model.",
         "We estimated transmission with a renewal model.",
         "Circle every -tion noun in a paragraph. Wherever someone does that "
         "action, try saying it as a verb.",
         "§5.2.4", rules=("G102", "G103")),
    Card("passive-voice", "Active and passive voice", "Sentences",
         "Passive suits Methods; a named doer is usually better active.",
         "Passive is right when the doer does not matter, which is why it is "
         "fine in Methods ('samples were stored at 4 °C'). When the doer is "
         "named in a 'by' phrase, the active form is shorter and puts the "
         "actor first. Choose by what belongs at the start of the sentence.",
         "A similar pattern was reported by Lim and colleagues in a "
         "neighbouring region.",
         "Lim and colleagues reported a similar pattern in a neighbouring "
         "region.",
         "In your Discussion, look for 'by' after 'was' or 'were'. Each one "
         "is a sentence you could turn round.",
         "§5.2.3+§6", rules=("G104",)),
    Card("topic-and-stress", "Begin with the familiar, end with the news",
         "Sentences",
         "The start says whose story it is; the end carries the point.",
         "Readers expect the start of a sentence to say whose story it is "
         "and the end to carry what is new. Openers such as 'There are' or "
         "'It is important to note that' spend the start on nothing, and "
         "endings such as 'as previously reported' push the finding into "
         "the middle. Start with the subject that matters and end on the news.",
         "It is important to note that transmission was highest in the "
         "densest district, according to our estimates.",
         "In our estimates, transmission was highest in the densest district.",
         "Read only the last few words of each sentence in a paragraph. "
         "They should be the points you want remembered.",
         "§5.2.2+§5.2.3", rules=("G105", "G108")),
    Card("long-sentences", "One idea per sentence", "Sentences",
         "A very long sentence usually carries two or three ideas.",
         "A sentence of more than about fifty words usually carries two or "
         "three ideas, and the reader must decide which one matters. Some "
         "long sentences work, such as a careful definition or a list, so "
         "this is a prompt to check, not a rule to obey. Where the ideas are "
         "separate, give each its own sentence.",
         "We fitted the model to the three districts jointly because a joint "
         "fit lets them share information about the incubation period, "
         "which no single district identifies well, and because it shows "
         "whether the districts differ in transmission or only in reporting, "
         "which decides where control should go first.",
         "We fitted the model to the three districts jointly. A joint fit "
         "lets them share information about the incubation period, which no "
         "single district identifies well. It also shows whether the "
         "districts differ in transmission or only in reporting, which "
         "decides where control should go first.",
         "If you need to breathe twice to read a sentence aloud, look for "
         "the place to split it.",
         "§5.2", rules=("G106",)),
    Card("noun-stacks", "Unpack stacked nouns", "Sentences",
         "Four nouns in a row make the reader guess how they relate.",
         "A run of four or more nouns ('district case report delay "
         "distribution') leaves the reader to work out how each relates to "
         "the next. Unpack it with a preposition or two, so the relations "
         "are said rather than guessed. Readers from a neighbouring field "
         "will thank you most.",
         "The district case report delay distribution was estimated first.",
         "We first estimated the distribution of delays in reporting cases "
         "from each district.",
         "Look for runs of nouns with no 'of', 'in' or 'for' between them, "
         "and read each run to a colleague outside your field.",
         "§5.2+§9.1", rules=("G107",)),
    Card("flow", "Link one sentence to the next", "Sentences",
         "Each sentence should pick up something from the one before.",
         "A paragraph flows when each sentence picks up something from the "
         "one before. Two 'However's in a row make the reader turn twice, "
         "and a bare 'This' at the start of a sentence makes them guess what "
         "'this' is. Name the thing ('This delay'), and keep contrast words "
         "for real changes of direction.",
         "Cases rose in May. However, reporting was delayed. However, the "
         "peak was clear. This suggests early control.",
         "Cases rose in May. Reporting was delayed, but the peak was still "
         "clear. This early peak suggests that control should start in April.",
         "Read only the first three words of each sentence in a paragraph: "
         "they should hand the reader from one idea to the next.",
         "§5.1+lecture", rules=("E702", "E703")),
    # --- Words ----------------------------------------------------------------------
    Card("concise-words", "Say it in fewer words", "Words",
         "Padding phrases add length, not meaning.",
         "Phrases such as 'due to the fact that', 'it should be noted that', "
         "'each and every' and 'in terms of' add length without meaning. "
         "Readers skim them, and they dilute the sentences that matter. Use "
         "the short form: 'because', the point itself, 'each', or the "
         "relation you actually mean.",
         "Due to the fact that reporting was delayed, it should be noted that "
         "the most recent weeks were excluded in terms of the fit.",
         "Because reporting was delayed, we excluded the most recent weeks "
         "from the fit.",
         "Cut every phrase you could delete without changing what the "
         "sentence claims.",
         "§6", rules=("W202", "W205", "W206", "W209")),
    Card("plain-words", "Plain, concrete words", "Words",
         "Grand words and vague adjectives say less than plain ones.",
         "Grand words ('utilise', 'facilitate'), buzzwords ('novel', "
         "'cutting-edge'), intensifiers ('very', 'extremely') and vague "
         "comparisons ('relatively high') sound weighty but say less than "
         "plain ones. Prefer the ordinary word, and replace an adjective with "
         "the number or the comparison it stands for: higher than what, and "
         "by how much?",
         "This novel framework sheds light on the relatively high burden in "
         "very dense districts.",
         "The model attributes 60% of cases to the two densest districts, "
         "which hold 35% of the population.",
         "For every adjective of size or importance, ask: compared with what? "
         "Then give that comparison.",
         "§6+lecture", rules=("W201", "W203", "W204", "E701", "E706")),
    Card("abbreviations-and-terms", "Define once, then keep to it", "Words",
         "One definition, before first use; one form of each term.",
         "Define an abbreviation at its first use, once, and then use it. An "
         "abbreviation used only once is not worth defining. Keep one form of "
         "each term throughout: 'dataset' and 'data set' on the same page "
         "make a careful reader wonder whether they are two things.",
         "The extrinsic incubation period (EIP) shortens with heat. Later: "
         "the extrinsic incubation period (EIP) was fixed, and the data set "
         "and the dataset were merged.",
         "The extrinsic incubation period (EIP) shortens with heat. Later: "
         "the EIP was fixed at ten days, and the two datasets were merged.",
         "Search for each abbreviation's definition: there should be exactly "
         "one, before its first use.",
         "§9.1", rules=("F601", "F612", "F613", "W211")),
    # --- Claims and evidence -------------------------------------------------------
    Card("hedging", "Calibrate your confidence", "Claims and evidence",
         "One qualifier, matched to the evidence, beats several.",
         "Hedges ('may', 'suggest') and boosters ('clearly', 'obviously') "
         "tell the reader how far to trust a claim. Stacked hedges ('may "
         "possibly suggest') read as doubt about the writing, not the "
         "science, and 'clearly' asks the reader to agree instead of showing "
         "why. Use one qualifier that matches the evidence, and let the "
         "evidence carry the confidence.",
         "These results may possibly suggest that the campaign clearly "
         "reduced transmission.",
         "These results suggest that the campaign reduced transmission.",
         "Read your Discussion for hedges and boosters only. Each claim "
         "should carry one, matched to its evidence.",
         "§4+§9.3", rules=("C301", "C305")),
    Card("overclaiming", "Claim no more than the evidence shows",
         "Claims and evidence",
         "'Proves' invites a reviewer to find the exception.",
         "'Prove', 'conclusively' and 'establishes' belong to mathematics and "
         "to rare, overwhelming evidence. A model fit or an observational "
         "study supports, suggests or is consistent with a claim. "
         "Overclaiming invites a reviewer to look for the one case that "
         "breaks it.",
         "This proves that housing density drives transmission.",
         "This is consistent with housing density driving transmission, "
         "although the districts also differ in other ways.",
         "Search your draft for 'prove' and 'demonstrate'. Keep them only "
         "where a reviewer could not reasonably disagree.",
         "§4", rules=("C302",)),
    Card("causal-language", "Causal words need a causal design",
         "Claims and evidence",
         "Say what your design supports: cause, or association.",
         "Verbs such as 'reduced', 'caused' and 'drives' claim that one thing "
         "made another happen. That is fair from a randomised trial and "
         "risky from observational data or a model, where 'was associated "
         "with' or 'in the model, X reduced Y' is accurate. You know your "
         "design; the point is to say what it supports.",
         "Vector control reduced dengue incidence by 30%.",
         "Districts with vector control had 30% lower incidence; the "
         "difference may partly reflect other differences between districts.",
         "For each causal verb, ask what would have to be true of the design "
         "for a sceptic to accept it.",
         "§9.4", rules=("C303",)),
    Card("significance", "Say which 'significant' you mean",
         "Claims and evidence",
         "A passed test, or an effect that matters? Give the number.",
         "'Significant' can mean that a statistical test passed or that an "
         "effect is large enough to matter, and readers cannot tell which. "
         "If you mean the test, give the estimate and its interval; if you "
         "mean importance, give the size of the effect and say why it matters.",
         "The effect of rainfall was significant.",
         "Each additional 10 mm of weekly rainfall was associated with 4% "
         "more cases (95% CI 1% to 7%).",
         "Replace every bare 'significant' with the number it summarises.",
         "§9.3", rules=("C304",)),
    Card("who-says", "Who says? Cite what is known and what is new",
         "Claims and evidence",
         "Claims about the literature need a citation or a boundary.",
         "'It is known that', 'is considered to be' and 'has never been "
         "studied' are claims about the literature. Without a citation the "
         "reader cannot check them, and an absolute 'never' can be refuted by "
         "one paper. Cite the source, or narrow the claim to what you "
         "checked: 'to our knowledge'.",
         "It is known that dengue transmission is sensitive to temperature, "
         "and this has never been studied in lowland districts.",
         "Dengue transmission is sensitive to temperature (Lim et al., 2021). "
         "To our knowledge, no study has measured this in lowland districts.",
         "Highlight every sentence about what is known or unknown. Each one "
         "needs a citation or 'to our knowledge'.",
         "lecture+§4", rules=("E704", "E705")),
    Card("warranting", "Claims need a warrant", "Claims and evidence",
         "Say why the evidence supports the claim: the 'because'.",
         "An argument has three parts: the claim, the evidence for it, and "
         "the warrant, which says why that evidence supports that claim. "
         "Discussions often state the claim and show the data but leave the "
         "link unsaid. Say it: 'this suggests that ..., because ...'.",
         "Transmission was highest in Marrowick. Housing is densest there. "
         "Control should focus on Marrowick.",
         "Transmission was highest in Marrowick, where housing is densest; "
         "denser housing brings people and mosquitoes closer, which would "
         "raise transmission. Control should therefore start there.",
         "For each claim in your Discussion, find its 'because'. If it is "
         "missing, add it.",
         "WW+Toulmin+§4"),
    # --- Figures, tables and numbers ------------------------------------------------
    Card("figures-and-tables", "Figures and tables carry the argument",
         "Figures, tables and numbers",
         "Cite each one, in order; lead with the finding, not the figure.",
         "Cite every figure and table in the text, in the order they are "
         "numbered, before they appear; a reference to a figure that does "
         "not exist is a broken promise. A caption should let the figure be "
         "read on its own: what is plotted, and what the reader should see. "
         "In the text, lead with the finding and point to the figure in "
         "brackets, rather than opening with 'Figure 1 shows'.",
         "Figure 2 shows the model fit. Figure 1 shows the cases by district.",
         "Cases peaked three weeks earlier in Marrowick than in Oldmere "
         "(Figure 1), and the model reproduced the timing in every district "
         "(Figure 2).",
         "List your figures and tables in the order the text first cites "
         "them. The list should read 1, 2, 3.",
         "ICMJE+§9.7+lecture",
         rules=("X101", "X102", "X103", "X104", "X202", "E707")),
    Card("numbers-and-units", "Numbers that agree", "Figures, tables and numbers",
         "A number in the text must be the number in its table.",
         "A number quoted in the text should be the number in the table it "
         "cites; one mismatch makes a reviewer distrust every other number. "
         "Write a unit the same way every time, with a space after the "
         "number, and do not start a sentence with a numeral: spell it out "
         "or rephrase.",
         "The attack rate was 4.8% in Marrowick (Table 1, which says 4.2%). "
         "26 weeks were analysed, with incubation of 5.9days.",
         "The attack rate was 4.2% in Marrowick (Table 1). We analysed 26 "
         "weeks, with a mean incubation period of 5.9 days.",
         "Check each number in your Results against its table, line by line, "
         "once, before you submit.",
         "§6+SI+AMA", rules=("X401", "N101", "N102")),
    Card("equations", "Equations are sentences", "Figures, tables and numbers",
         "Lead in, display, then say what the symbols mean.",
         "A displayed equation is part of the sentence around it: the words "
         "before it lead in ('the force of infection is'), and the words "
         "after it interpret it ('where N is the population'). An equation "
         "dropped in after a full stop arrives unannounced. Number an "
         "equation only if the text refers to it.",
         "We assume mass action. [λ = βI/N] N is the population.",
         "Under mass action, the force of infection is [λ = βI/N], where N "
         "is the population.",
         "Read each equation aloud as part of its sentence. If the sentence "
         "does not survive, add the lead-in or the 'where'.",
         "§9.2", rules=("X301", "X302")),
    # --- Structure and argument ---------------------------------------------------
    Card("abstract", "The abstract in six moves", "Structure and argument",
         "Known, missing, asked, done, found, why it matters.",
         "Readers decide from the abstract whether to read on. A good "
         "abstract answers six things in order: what is known, what is "
         "missing, what you asked, how you did it, what you found, and why it "
         "matters. Give at least one real finding with its size; 'results "
         "will be discussed' tells the reader nothing.",
         "Dengue is common. We fitted a model to case data. The results are "
         "discussed in terms of their implications.",
         "Dengue seasons vary widely between districts, but why is unclear. "
         "We asked whether transmission or reporting explains the difference, "
         "fitting a transmission model to weekly cases from three districts. "
         "Transmission was twice as high in the densest district, while "
         "reporting was similar, so control should start there.",
         "Label each sentence of your abstract with one of the six moves. "
         "Every move should appear once, in order.",
         "course-U2", rules=("AB801", "AB802")),
    Card("introduction", "The introduction: territory, gap, aim",
         "Structure and argument",
         "Why it matters, what is unknown, how this work fills it.",
         "An introduction makes three moves: why the area matters, what is "
         "still unknown, and how this work fills that gap. The gap is the "
         "hinge; without it the reader cannot see why the work was needed. A "
         "list of earlier studies ('There are many studies on ...') is not a "
         "gap. The gap is what those studies leave open.",
         "There are many studies on dengue. Lim et al. studied temperature. "
         "Quintero studied rainfall. We studied three districts.",
         "Dengue seasons vary widely between districts. Earlier studies "
         "linked this to temperature and rainfall, but none separated "
         "transmission from reporting. We therefore asked whether the "
         "districts differ in transmission or only in what is reported.",
         "Find the sentence in your introduction that says what is unknown. "
         "If you cannot point to it, write it.",
         "Swales+Shehzad+§3", rules=("D902", "L901")),
    Card("methods-reporting", "Methods a reader could repeat",
         "Structure and argument",
         "The data first, then the analysis and its assumptions.",
         "A methods section lets a reader judge the results and, in "
         "principle, repeat the work. Start with the data (what, where, when, "
         "on whom), then the analysis: the model or test, how it was fitted, "
         "and the assumptions it makes. Passive voice is fine here, because "
         "the procedure matters more than who did it.",
         "A model was used on the data.",
         "We used weekly dengue counts from the clinics of three districts, "
         "April to September 2022, and fitted an SEIR model to them by "
         "Hamiltonian Monte Carlo, assuming a mean infectious period of five "
         "days.",
         "Give your methods to a colleague and ask what they would need to "
         "redo the analysis. Add it.",
         "§2+§9.5"),
    Card("results-reporting", "Results: the finding first", "Structure and argument",
         "Open with the finding; give the number and its uncertainty.",
         "Each results paragraph should open with the finding, give the "
         "number with its uncertainty, and point to the figure or table that "
         "shows it. Keep interpretation for the discussion, but do say what "
         "the number is: an estimate without its interval is half a result.",
         "Table 2 shows the estimates.",
         "The basic reproduction number was highest in Marrowick, at 2.1 "
         "(95% CrI 1.8 to 2.4; Table 2).",
         "Check that every paragraph of your Results starts with a finding, "
         "not with a figure.",
         "§2+§9.3+§9.7"),
    Card("discussion", "The discussion: from finding to meaning",
         "Structure and argument",
         "Finding, meaning, earlier work, limits, what should change.",
         "A discussion widens out again. Restate the main finding in one "
         "sentence, say what it means and why, compare it with earlier work, "
         "state the limitations yourself, and end with what should change and "
         "for whom. A limitation you state is a boundary; one a reviewer finds "
         "is a rebuttal.",
         "Our results are interesting. Further research is needed.",
         "Transmission, not reporting, explained the difference between "
         "districts, as earlier work in a neighbouring region suggested. Our "
         "weekly data cannot show the direction of spread. Vector control "
         "should start first in the densest district.",
         "Mark the five moves in your discussion's margin: finding, meaning, "
         "comparison, limitation, implication.",
         "§2+WW+§9.8"),
    # --- Mechanics ------------------------------------------------------------------
    Card("spelling-and-grammar", "Spelling, grammar and slips", "Mechanics",
         "Small slips cost trust out of proportion to their size.",
         "A reader who meets a misspelt word or a doubled 'the' starts to "
         "wonder what else was rushed. The checks catch most slips, but they "
         "also flag technical words they do not know: add those to your "
         "dictionary once. Pick one spelling convention, UK or US, for the "
         "whole document, and keep contractions such as 'don't' for "
         "informal writing.",
         "We fitted an renewal model to the the weekly counts.",
         "We fitted a renewal model to the weekly counts.",
         "Before you send a draft, read it aloud once, slowly: the ear "
         "catches doubled words the eye skips.",
         "§6+LanguageTool+symspellpy",
         rules=("S001", "LT001", "W207", "GEC001", "W210", "W208")),
    Card("headings", "Headings as structure", "Mechanics",
         "Heading styles for headings only; body styles for text.",
         "In Word, the heading styles build the navigation pane, the table of "
         "contents and the section structure every checker reads. A paragraph "
         "of body text in a heading style breaks all three, and a heading "
         "typed as bold body text is invisible to them. Use heading styles "
         "for headings and body styles for text.",
         "A whole paragraph of text formatted as Heading 1.",
         "The word 'Methods' in Heading 1, and the paragraph after it in the "
         "Normal style.",
         "Open Word's navigation pane: it should list only your headings, "
         "in order.",
         "Word", rules=("X501",)),
)

CARDS: dict = {c.id: c for c in _CARDS}

RULE_CARD: dict = {r: c.id for c in _CARDS for r in c.rules}

# The narrative map's moves lead to the card for their section; within the
# discussion, the warrant has its own card.
_SECTION_CARD = {
    "abstract": "abstract", "introduction": "introduction",
    "methods": "methods-reporting", "results": "results-reporting",
    "discussion": "discussion", "limitations": "discussion",
    "conclusion": "discussion",
}
_MOVE_CARD = {"interpretation": "warranting"}
# The argument's missing links (discourse/argument.py codes).
LINK_CARD = {
    "claim_without_warrant": "warranting",
    "claim_without_grounds": "warranting",
    "evidence_without_interpretation": "warranting",
    "limitation_not_reflected_in_claim_strength": "hedging",
    "contribution_unclear": "discussion",
}


def card_for_rule(rule_id: str):
    """The card id a rule's suggestions point to, or None."""
    return RULE_CARD.get(rule_id)


def card_for_move(section: str, move_id: str):
    return _MOVE_CARD.get(move_id) or _SECTION_CARD.get(section)


def card_for_link(code: str):
    return LINK_CARD.get(code)


def listing() -> list:
    """Every card, grouped in reading order: the Learn index."""
    order = {g: i for i, g in enumerate(GROUPS)}
    return [c.to_dict() for c in sorted(_CARDS,
                                        key=lambda c: order[c.group])]


def export_json(path) -> None:
    """Write the cards for the web's static Learn pages
    (packages/contract/learn.json). tests/test_learn.py fails when the
    committed file and the engine disagree: run
    `python -m researchly.learn packages/contract/learn.json`."""
    import json
    from pathlib import Path
    Path(path).write_text(json.dumps({"cards": listing()}, indent=2,
                                     ensure_ascii=False) + "\n",
                          encoding="utf-8")


if __name__ == "__main__":
    import sys
    export_json(sys.argv[1])
