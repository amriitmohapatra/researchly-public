"""Rhetorical moves per section: the authored questions behind the
narrative map (S4; ARCHITECTURE.md ADR-05).

Each move is a question a reader asks of a section ("Does the
Introduction say what is missing?"), with the source the question comes
from, a lesson in everyday words and a fill-in frame in Researchly's own
wording. The signals that find a move are regular expressions over one
sentence, shared with the abstract lens and the argument model so the
three never disagree about what an aim or a limitation looks like.

What a user sees (question, plain, frame) must not name this repository's
internals (CLAUDE.md #6; `test_explanations.INTERNAL`). The source code is
expanded to a full citation by `sources.cite` and shown on its own line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import sources
from . import abstract_lens
from . import argument


@dataclass(frozen=True)
class Move:
    id: str
    label: str
    question: str
    source: str          # a code for sources.cite()
    plain: str           # the lesson, in everyday words
    frame: str           # a fill-in frame, Researchly's own wording
    signals: tuple       # regexes over one sentence (case-insensitive)
    # An opening move: also present when the section's first sentence
    # makes none of the later moves (it sets the scene by not jumping in).
    opening: bool = False

    def matches(self, sentence: str) -> bool:
        return any(re.search(rx, sentence, re.IGNORECASE)
                   for rx in self.signals)

    @property
    def citation(self) -> str:
        return sources.cite(self.source)


_A = abstract_lens.SIGNALS
_R = argument._SIGNALS

# A gap in one sentence: a strong gap phrase, or a contrast word with a
# gap word in the same sentence ("However, ... remains unclear").
_GAP_STRONG = (
    r"\bremains? (unclear|unknown|unexplored|unquantified|limited|"
    r"uncertain|poorly understood|to be (seen|determined|established))\b",
    r"\blittle is known\b", r"\bfew(er)? studies\b",
    r"\b(has|have) (not|never|yet to) been\b", r"\bhas yet to\b",
    r"\blimited (evidence|research|data|understanding|insight)\b",
    r"\bgap in (the |our )?(literature|knowledge|understanding)\b",
    r"\bpaucity\b", r"\bunderstudied\b", r"\boverlooked\b",
    r"\bno (study|studies|previous work) (has|have)\b",
    r"\bwhat remains (unclear|unknown)\b",
    r"(?=.*\b(however|although|yet|but|nevertheless|despite)\b)"
    r"(?=.*\b(unclear|unknown|unexplored|unquantified|uncertain|not been|"
    r"rarely|seldom|lacking|lack of|missing|neglected)\b)",
)

_SUMMARY = (
    r"\b(in this (study|paper|work|thesis|chapter)|here),? we\b",
    r"\b(we|this study|our (model|analysis|results|estimates|fit))\b[^.;]*"
    r"\b(found|find|show|showed|shows|suggest|suggests|estimated|"
    r"reproduced|demonstrated|identified) (that|how|whether|no|a|the)\b",
    r"\b(we|our (results|findings|analysis|model)) (found|find|show|showed|"
    r"shows|suggest|suggests|estimate|estimated|demonstrate|demonstrated|"
    r"observed|report)\b",
    r"\b(our|the) (main|key|principal|central) (finding|result)s?\b",
)

_COMPARISON = (
    r"\b(consistent|in line|in agreement|in keeping|at odds|in contrast|"
    r"compared) with (previous|prior|earlier|other|those|estimates|"
    r"findings|reports|studies|work)\b",
    r"\b(previous|prior|earlier|other) (studies|work|estimates|reports|"
    r"analyses)\b",
    r"\bet al\b", r"\((19|20)\d{2}[a-z]?\)",
    r"\b(agrees?|agreed|differs?|differed|contrasts?) (with|from)\b",
    r"\b(higher|lower|larger|smaller|similar) (than|to) (those|that|"
    r"estimates|values) (reported|found|observed)\b",
)

_IMPLICATIONS = (
    r"\b(practical|policy|clinical|operational) (use|uses|implications?|"
    r"value|relevance|consequences?)\b",
    r"\bcould be (run|used|applied|adopted|repeated|extended) (at|by|in|"
    r"to|for|before|after|each|every)\b",
    r"\b(could|would|should|can) (be used to |help to |serve to )?"
    r"(rank|prioriti[sz]e|target|guide|inform|time|plan|allocate|focus|"
    r"direct|support) \b",
    r"\b(would|could) have the (most|greatest|largest) (effect|impact|"
    r"benefit)\b",
    r"\b(the|each) next (season|outbreak|epidemic|wave|step|study)\b",
)

_CONTRIBUTION = (
    r"\b(the|this|our) (approach|method|model|framework|analysis|study|"
    r"work) (needs|requires|provides|offers|allows|makes it possible|"
    r"enables|adds|extends|shows|showed|demonstrates|is the first)\b",
    r"\b(we|this work|this paper) (provide|present|introduce|propose|"
    r"extend|offer|report) (a|an|the|new)\b",
)

_DATA = (
    r"\bdata (from|were|was|on|set)\b", r"\bdataset\b",
    r"\bwere (recruited|collected|included|enrolled|obtained|extracted|"
    r"reported|sampled)\b",
    r"\b(surveillance|case (counts|notifications|reports)|registry|"
    r"cohort|survey|census|time series)\b",
    r"\bwe (collected|obtained|used|extracted|compiled|assembled) "
    r"(the |weekly |daily |monthly )?(data|counts|records|cases)\b",
)

_ANALYSIS = (
    r"\bwe (fitted|fit|developed|applied|analy[sz]ed|model(led|ed)|"
    r"simulated|estimated|calibrated|implemented|assumed|compared|"
    r"computed|derived|specified|sampled)\b",
    r"\b(seir|sir|compartmental|branching process|regression|agent-based|"
    r"transmission|renewal|bayesian|hierarchical|mixed) model\b",
    r"\b(likelihood|posterior|priors?|markov chain|mcmc|least squares|"
    r"maximum likelihood|sensitivity analys[ie]s)\b",
    r"\bwas (fitted|estimated|modelled|modeled|computed|derived|"
    r"calculated|simulated|calibrated)\b",
)

MOVES: dict = {m.id: m for m in (
    Move("territory", "Why it matters",
         "Does the opening say why this area matters?",
         "Swales+§3",
         "A reader needs a reason to care before they can care about your "
         "gap. One or two sentences on the size of the problem or the "
         "state of the field do it.",
         "“[Topic] is a major [burden / challenge / question] in "
         "[setting], because [consequence].”",
         tuple(_R["background"]) + (
             r"\b(is|are|remains?) (a|an|the|among the) (major|leading|"
             r"significant|growing|important|common|key)\b",
             r"\b(affects?|affecting|infects?) (millions|thousands|"
             r"\d[\d,.]* (million|thousand|people))\b",
             r"\b(public health|clinical|economic) (burden|importance|"
             r"priority|concern)\b"),
         opening=True),
    Move("gap", "What is missing",
         "Does the Introduction say what is still unknown?",
         "Swales+Shehzad+§3",
         "The gap is the hinge of an introduction: what the field does not "
         "yet know, and why that matters. Without it the reader cannot see "
         "why your work was needed.",
         "“Although [what is known], little is known about [the "
         "specific unknown], so [the consequence of not knowing].”",
         _GAP_STRONG),
    Move("aim", "What you set out to do",
         "Is there a sentence that says what this work set out to answer?",
         "Swales+§3",
         "After the gap, one sentence says how this work fills it: the "
         "question, the aim or the hypothesis. Readers look for it at the "
         "end of the introduction.",
         "“We therefore set out to [determine / estimate / test] "
         "[the research question].”",
         tuple(_A["aim"]) + (
             r"\bwe (therefore|thus|then|here|first|also|now) "
             r"(aim|aimed|set out|sought|seek|investigate|investigated|"
             r"examine|examined|estimate|estimated|test|tested|ask|asked|"
             r"quantify|quantified|assess|assessed|explore|explored)\b",
             r"\b(the present|this) (study|paper|work|analysis|chapter) "
             r"(aims?|aimed|sets? out|seeks|sought|estimates?|quantifies|"
             r"tests?|asks?|examines?|investigates?|explores?)\b",
             r"\bour (aim|objective|goal|purpose|question) (was|is|were)\b")),
    Move("background", "What is known",
         "Does the abstract open with what is already known?",
         "course-U2",
         "An abstract starts from the reader's current understanding, in "
         "one sentence, before it says what was missing.",
         "“Studies of [topic] generally find that [current "
         "consensus].”",
         tuple(_R["background"]), opening=True),
    Move("methods", "How it was done",
         "Does the abstract say how the question was answered?",
         "course-U2",
         "One sentence on the design, the data and the analysis lets the "
         "reader judge the findings before reading them.",
         "“We [fitted / analysed / surveyed] [model, design or data] "
         "from [setting, period].”",
         tuple(_A["methods"])),
    Move("findings", "What was found",
         "Does this section state what was found, with substance?",
         "course-U2+§2",
         "Findings are the point of the paper: give the main result with "
         "its size and its uncertainty, not a promise that results will "
         "be discussed.",
         "“[Main outcome] was [value, with uncertainty] in [group], "
         "compared with [comparator].”",
         tuple(_A["findings"])),
    Move("significance", "Why it matters now",
         "Does the ending say what the findings mean for the field or "
         "for practice?",
         "course-U2+§2",
         "The last move widens back out: what should change, and for "
         "whom, because of what was found.",
         "“This means that [field / practice] should [specific "
         "change].”",
         tuple(_A["significance"])),
    Move("data", "The data",
         "Do the Methods say where the data came from?",
         "§2",
         "A reader of the methods first wants the data: what was measured, "
         "where, when and on whom.",
         "“We used [data] from [source] covering [setting, period], "
         "comprising [size].”",
         _DATA),
    Move("analysis", "The analysis",
         "Do the Methods say how the data were analysed?",
         "§2",
         "After the data, the model or the analysis: what was fitted, how, "
         "and under what assumptions.",
         "“We fitted [model] to [data] by [method], assuming "
         "[assumptions].”",
         _ANALYSIS),
    Move("evidence", "The evidence",
         "Do the Results point to numbers, figures or tables?",
         "§9.7",
         "Results rest on evidence the reader can see: a number with its "
         "uncertainty, a figure or a table referred to by name.",
         "“[Outcome] was [value] (95% CI [low] to [high]; Figure "
         "[n]).”",
         tuple(_R["evidence"])),
    Move("summary", "The main finding, restated",
         "Does the Discussion open by restating the main finding?",
         "§2",
         "A discussion starts where the results ended: the main finding "
         "in one sentence, before interpreting it.",
         "“In this study we found that [main finding].”",
         _SUMMARY),
    Move("interpretation", "What it means",
         "Does the Discussion say why the evidence supports the claims?",
         "WW+Toulmin+§4",
         "A claim needs a warrant: the sentence that says why the evidence "
         "supports it. Readers are given the claim and the data; the link "
         "between them is the author's job.",
         "“This suggests that [claim], because [why the evidence "
         "supports it].”",
         tuple(_R["warrant"])),
    Move("comparison", "Against earlier work",
         "Does the Discussion compare the findings with earlier work?",
         "§3+§7.3",
         "Readers place a finding by what came before: say whether it "
         "agrees with earlier studies, and if not, why.",
         "“Our estimate is [consistent with / higher than] [earlier "
         "work], which [reason].”",
         _COMPARISON),
    Move("limitations", "What this cannot show",
         "Does the Discussion state the limitations?",
         "WW+§4",
         "A limitation stated by the author pre-empts the reviewer's "
         "rebuttal. Say what the data or the design cannot show, and "
         "what that does to the conclusions.",
         "“This study has limitations. First, [constraint], which "
         "means [bounded consequence].”",
         tuple(_R["limitation"])),
    Move("implications", "What should change",
         "Does the ending say what a reader could do with this?",
         "§2+§9.8",
         "The hourglass widens back out at the end: a plain, honestly "
         "qualified statement of what the findings mean for practice or "
         "for the next study.",
         "“[Decision-makers] could use this to [action], provided "
         "[condition].”",
         tuple(_R["implication"]) + tuple(_A["significance"]) + _IMPLICATIONS),
    Move("contribution", "What this adds",
         "Does the ending say what this work adds to the field?",
         "WW+§3",
         "Say plainly what is new: the reader should not have to work "
         "out the contribution for themselves.",
         "“This work adds [contribution] to [the field].”",
         tuple(_R["contribution"]) + _CONTRIBUTION),
)}

# What each section is expected to do, in order. Sections not listed
# (appendix, references, topical headings) are not mapped.
SCHEMAS: dict = {
    "abstract": ("background", "gap", "aim", "methods", "findings",
                 "significance"),
    "introduction": ("territory", "gap", "aim"),
    "methods": ("data", "analysis"),
    "results": ("findings", "evidence"),
    "discussion": ("summary", "interpretation", "comparison",
                   "limitations", "implications"),
    "limitations": ("limitations",),
    "conclusion": ("contribution", "implications"),
}

# Where the order of the moves is itself the advice.
ORDERED = frozenset({"abstract", "introduction"})

SECTION_LABELS = {
    "abstract": "Abstract", "introduction": "Introduction",
    "methods": "Methods", "results": "Results", "discussion": "Discussion",
    "limitations": "Limitations", "conclusion": "Conclusion",
}


def label_moves(sentence: str, section: str, first: bool = False) -> list:
    """The ids of the section's expected moves this sentence makes. The
    section's first sentence also makes its opening move (what is known,
    why it matters) when it makes none of the later moves."""
    schema = SCHEMAS.get(section, ())
    found = [m for m in schema if MOVES[m].matches(sentence)]
    if first and not found:
        found = [m for m in schema if MOVES[m].opening]
    return found
