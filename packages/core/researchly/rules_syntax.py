"""spaCy-based syntactic rules (Gopen & Swan sentence mechanics + hedging/causal).

These need POS tags and dependency structure: subject–verb distance, buried
actions, agent-ful passives, hedge stacking, causal-verb claims.
"""

from __future__ import annotations

import re

from . import lexicons as lx
from .document import Document
from .engine import Category, Suggestion, rule

SUBJECT_DEPS = {"nsubj", "nsubjpass"}


def _is_heading_line(document: Document, start: int) -> bool:
    """Skip fragments that are headings (they aren't sentences)."""
    return any(abs(h.start - start) < 3 for h in document.headings)


# ---------------------------------------------------------------------------
# G101 — subject–verb separation
# ---------------------------------------------------------------------------

@rule("G101", "subject-verb-separation", Category.IMPROVEMENT,
      "Long interruption between subject and verb.",
      'Readers hold their breath from the subject until the verb arrives; '
      'anything long jammed between them reads as an interruption and '
      "drains emphasis. Move the machinery out: 'The model predicts X. It "
      "incorporates A, B, and C.' rather than 'The model, which "
      "incorporates A, B, and C, predicts X.'",
      plain=('There are many words between the subject of this sentence and its '
             'verb. Readers wait for the verb and lose the thread. Move the '
             'extra material into its own sentence, or bring the verb closer to '
             'the subject.'),
      source="§5.2.1")
def g101_subject_verb(doc, document: Document):
    # Dogfooding tune (8 theses, v0.1): plain long subject noun phrases
    # (a head noun trailed by a chain of of/for/in prepositional phrases,
    # with no comma or clause inside) are ordinary academic register, and
    # flagging them at gap>=8 produced ~5.5 flags/1000 words. G&S's target
    # is the *interruption* — so we now require an interrupting structure
    # (comma-bounded clause, relative clause, apposition, parenthesis) in
    # the gap, and a gap of >= 10.
    #
    # Q3 tune (P31): of the 779 flags left on the theses, 158 were still
    # plain long subjects. A comma that separates list items ("Chad,
    # Iraq and Niger") or brackets holding a citation or an abbreviation
    # ("(239, 240)", "(LASSO)") interrupt nothing; and a restrictive
    # clause or bare apposition ("data collected from patients aged 1-17
    # ... revealed") is part of the subject, so it needs a longer gap.
    GAP, WEAK_GAP = 10, 15
    for tok in doc:
        if tok.dep_ in SUBJECT_DEPS and tok.head.pos_ in {"VERB", "AUX"}:
            head = tok.head
            if head.i <= tok.i:
                continue
            between = doc[tok.i + 1:head.i]
            gap = len([t for t in between
                       if not t.is_punct and not t.is_space])
            if gap < GAP:
                continue
            weak = any(t.dep_ in WEAK_INTERRUPT_DEPS for t in between)
            if _interrupts(between) or (weak and gap >= WEAK_GAP):
                yield Suggestion(
                    message=f"{gap} words separate "
                            f"'{tok.text}' from '{head.text}' — consider "
                            "moving the interrupting material after the verb.",
                    start=tok.idx,
                    end=head.idx + len(head.text))


# Part of the subject rather than an aside: these interrupt only when long.
WEAK_INTERRUPT_DEPS = {"relcl", "acl", "appos"}
_BRACKETS = {"(": ")", "[": "]"}


def _interrupts(span) -> bool:
    """A dash, a bracketed aside of 3+ words, a comma that is not a list
    separator, or an adverbial or parenthetical clause."""
    toks = list(span)
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t.text in {"—", "–"}:
            return True
        if t.text in _BRACKETS:
            inner = []
            for u in toks[i:]:
                if u.text == _BRACKETS[t.text]:
                    break
                inner.append(u)
            if sum(1 for u in inner if u.is_alpha) >= 3:
                return True
            i += len(inner) + 1               # "(12, 13)": skip it whole
            continue
        if t.text == ",":
            h = t.head
            if h.dep_ == "conj" or any(c.dep_ == "conj" for c in h.children):
                continue                      # separates list items
            return True
        if t.dep_ in {"advcl", "parataxis"}:
            return True
    return False


# ---------------------------------------------------------------------------
# G102 — buried action (light verb + nominalization)
# ---------------------------------------------------------------------------

def _conjugate(verb: str, light_tag: str) -> str:
    """Conjugate `verb` (base form) to match the light verb's tense/form.
    'performed an estimation' → 'estimated'; 'conducts a comparison' →
    'compares'; 'making an assessment' → 'assessing'."""
    if light_tag in {"VBD", "VBN"}:                       # past
        if verb.endswith("e"):
            return verb + "d"
        if len(verb) > 2 and verb.endswith("y") and verb[-2] not in "aeiou":
            return verb[:-1] + "ied"
        return verb + "ed"
    if light_tag == "VBZ":                                # 3sg present
        if verb.endswith(("sh", "ch", "s", "x", "z", "o")):
            return verb + "es"
        if len(verb) > 2 and verb.endswith("y") and verb[-2] not in "aeiou":
            return verb[:-1] + "ies"
        return verb + "s"
    if light_tag == "VBG":                                # gerund
        if verb.endswith("e") and not verb.endswith(("ee", "ye")):
            return verb[:-1] + "ing"
        return verb + "ing"
    return verb                                           # VB/VBP: base


@rule("G102", "buried-action", Category.IMPROVEMENT,
      "Action buried in a noun (performed an estimation → estimated).",
      'English readers look for the action of a sentence in its verb. '
      'When the action hides in a nominalization, the sentence goes limp. '
      'Turn the noun back into a verb and the prose comes alive and '
      'shortens by a third.',
      plain=("The action here is hidden in a noun, such as 'performed an "
             "estimation'. Use the verb instead: 'estimated'. The sentence "
             'becomes shorter and clearer.'),
      source="§5.2.4", fix_safety="safe")
def g102_buried_action(doc, document: Document):
    for tok in doc:
        if tok.pos_ != "VERB" or tok.lemma_.lower() not in lx.LIGHT_VERBS:
            continue
        for child in tok.children:
            if child.dep_ not in {"dobj", "obj"}:
                continue
            noun = child.lemma_.lower()
            verb = lx.NOMINAL_TO_VERB.get(noun) or lx.NOMINAL_TO_VERB.get(
                child.text.lower())
            if not verb:
                continue
            # Conjugate to the light verb's form so the fix is grammatical
            # in place: 'performed an estimation of' → 'estimated'.
            fixed = _conjugate(verb, tok.tag_)
            # Absorb a trailing 'of' ("estimation OF the rate"), so applying
            # the fix yields 'estimated the rate', not 'estimated of the
            # rate'.
            end = child.idx + len(child.text)
            of_children = [c for c in child.children
                           if c.dep_ == "prep" and c.lower_ == "of"
                           and c.i == child.i + 1]
            if of_children:
                end = of_children[0].idx + len(of_children[0].text)
            yield Suggestion(
                message=f"Put the action in the verb: '{fixed}'.",
                start=tok.idx, end=end,
                replacement=fixed)


# ---------------------------------------------------------------------------
# G103 — nominalization density
# ---------------------------------------------------------------------------

@rule("G103", "nominalization-density", Category.IMPROVEMENT,
      "Three or more nominalizations in one sentence.",
      'Each -tion/-ment/-ance word is a verb in a box. One is fine; three '
      'in a sentence and the prose reads as fog even though every word is '
      'correct. Hunt them, and un-box the most important one.',
      plain=('This sentence has several nouns made from verbs, such as '
             "'implementation' or 'assessment'. One is fine; three make the "
             'sentence hard to follow. Turn the most important one back into a '
             'verb.'),
      source="§5.2.4")
def g103_nominalization_density(doc, document: Document):
    for sent in doc.sents:
        if _is_heading_line(document, sent.start_char):
            continue
        # Dogfooding tune: a nominalization acting as a compound modifier
        # ("prediction models", "notification data") is technical vocabulary,
        # not a buried action. Count only free-standing nominals — the
        # "X of Y" pattern is the classic buried-action signature.
        nominals = [
            t for t in sent
            if t.pos_ == "NOUN"
            and t.dep_ != "compound"
            and len(t.text) >= lx.NOMINAL_MIN_LEN
            and t.text.lower().endswith(lx.NOMINAL_SUFFIXES)
            and t.text.lower() not in lx.NOMINAL_ALLOWLIST
        ]
        if len(nominals) >= 3:
            first, last = nominals[0], nominals[-1]
            names = ", ".join(t.text for t in nominals[:4])
            yield Suggestion(
                message=f"{len(nominals)} nominalizations here ({names}) — "
                        "convert at least the main action back into a verb.",
                start=first.idx, end=last.idx + len(last.text))


# ---------------------------------------------------------------------------
# G104 — passive voice with recoverable agent (section-aware)
# ---------------------------------------------------------------------------

@rule("G104", "passive-with-agent", Category.CONVENTION,
      "Passive with a stated agent ('was shown by X') — active is usually stronger.",
      'Active and passive both have jobs. Passive is right when the doer '
      "is irrelevant ('samples were incubated at 37 °C'), which is why "
      'this rule stays silent in Methods. But when the agent appears in a '
      "'by'-phrase, the sentence pays the passive's cost without its "
      "benefit: 'X showed' is shorter and puts the actor in the topic "
      'position. Choose by what belongs at the start of the sentence, not '
      'by habit.',
      plain=("This sentence is passive and names who did the action ('was shown "
             "by X'). The active form is shorter and puts the actor first: 'X "
             "showed'. Passive is fine in Methods, where the actor does not "
             'matter, so we never flag it there.'),
      sections_excluded=("methods", "appendix"),
      source="§6")
def g104_passive_agent(doc, document: Document):
    # Dogfooding tunes: (1) a by-phrase naming a method or grouping
    # criterion ("stratified by region"), not a doer, is not an agent-ful
    # passive; require a proper-noun (or person-like) agent. (2) A pronoun
    # subject ("It is distributed by X...") marks topic continuity — exactly
    # the case where the guide says the passive is RIGHT — so we stay
    # quiet.
    PERSON_LIKE = {"author", "authors", "researcher", "researchers",
                   "investigator", "investigators", "we"}
    for tok in doc:
        if tok.dep_ != "auxpass":
            continue
        verb = tok.head
        subj = [c for c in verb.children if c.dep_ == "nsubjpass"]
        if subj and subj[0].pos_ == "PRON":
            continue
        agents = [c for c in verb.children if c.dep_ == "agent"]
        for ag in agents:
            pobj = [c for c in ag.children if c.dep_ == "pobj"]
            if not pobj:
                continue
            agent_subtree = list(pobj[0].subtree)
            agent_is_doer = (
                any(t.pos_ == "PROPN" for t in agent_subtree)
                or pobj[0].lemma_.lower() in PERSON_LIKE)
            if not agent_is_doer:
                continue
            # A masked \\cite{} after the agent is a whitespace token in
            # its subtree; and a misparse can put the agent before the
            # auxiliary, giving a reversed span (P29 bench).
            words = [t for t in agent_subtree if not t.is_space]
            if not words:
                continue
            end_tok = max(words, key=lambda t: t.i)
            if end_tok.i < tok.i:
                continue
            yield Suggestion(
                message="Agent is stated — consider active voice: "
                        f"'{pobj[0].text} {verb.lemma_}…'.",
                start=tok.idx, end=end_tok.idx + len(end_tok.text))


# ---------------------------------------------------------------------------
# G105 — expletive openers
# ---------------------------------------------------------------------------

@rule("G105", "expletive-opener", Category.IMPROVEMENT,
      "Empty opener ('There are…', 'It is…that') wastes the topic position.",
      "The start of a sentence tells the reader whose story it is. 'There "
      "are three factors that drive transmission' gives that slot to "
      "nobody; 'Three factors drive transmission' gives it to the "
      'factors.',
      plain=("'There are' or 'It is' at the start of a sentence gives the first "
             "words to nothing. Start with the real subject: 'Three factors "
             "drive transmission' instead of 'There are three factors that drive "
             "transmission'."),
      source="§5.2.3")
def g105_expletive(doc, document: Document):
    for sent in doc.sents:
        if _is_heading_line(document, sent.start_char):
            continue
        m = re.match(r"\s*(There (?:is|are|was|were|has been|have been)\b"
                     r"|It (?:is|was) \w+ that\b)",
                     sent.text, re.IGNORECASE)
        if m:
            yield Suggestion(
                message="Start with the real subject instead.",
                start=sent.start_char + m.start(1),
                end=sent.start_char + m.end(1))


# ---------------------------------------------------------------------------
# G106 — overlong sentence
# ---------------------------------------------------------------------------

@rule("G106", "overlong-sentence", Category.IMPROVEMENT,
      "Sentence over 50 words — check it carries one idea.",
      'Not an error: some long sentences earn their length. But past '
      'about 40 words, check whether this is one idea or two ideas '
      'sharing a sentence. If you stumble reading it aloud, the reader '
      'will stumble too.',
      plain=('This sentence is very long. Long sentences are not wrong, but '
             'check whether it carries one idea or two. If you would pause for '
             'breath reading it aloud, split it there.'),
      source="§5.1")
def g106_overlong(doc, document: Document):
    # Dogfooding tune: in 8 accepted theses the p90 sentence length was 48
    # words — a 40-word threshold flagged ~17% of all sentences (noise).
    # 50 targets the genuinely unwieldy tail (~7%). Sentences dense in
    # digits/symbols (inline equations, stat reporting runs) are skipped:
    # their "length" is not prose length.
    LIMIT = 50
    for sent in doc.sents:
        if _is_heading_line(document, sent.start_char):
            continue
        toks = [t for t in sent if not t.is_punct and not t.is_space]
        n = len(toks)
        nonword = sum(1 for t in toks if not t.is_alpha)
        if n > LIMIT and (nonword / n) < 0.25:
            # From the first to the last real token: a sentence that follows
            # masked markup (a LaTeX preamble) starts with whitespace tokens.
            first = next(t for t in sent if not t.is_space)
            last = [t for t in sent if not t.is_space][-1]
            yield Suggestion(
                message=f"{n} words — consider splitting at a natural seam "
                        "(often at 'and', 'which', or a semicolon).",
                start=first.idx, end=last.idx + len(last.text))


# ---------------------------------------------------------------------------
# G107 — long noun strings
# ---------------------------------------------------------------------------

@rule("G107", "noun-string", Category.IMPROVEMENT,
      "Four or more stacked nouns — unpack with prepositions.",
      "'Income quintile contact matrix estimation procedure' forces the "
      "reader to parse backwards from the last noun. Unpack it: 'the "
      "procedure for estimating contact matrices by income quintile'.",
      plain=('Several nouns are stacked in a row here, and the reader has to '
             "work backwards to understand them. Add small words like 'of' and "
             "'for': 'the procedure for estimating contact matrices' is easier "
             "than 'contact matrix estimation procedure'."),
      source="§6")
def g107_noun_string(doc, document: Document):
    def is_citation_like(tokens) -> bool:
        # Dogfooding tunes: named entities and established technical terms
        # ("Markov chain Monte Carlo", "World Health Organization guideline",
        # "Aedes aegypti") read as units, not stacks — skip runs with 2+
        # proper nouns. Also skip runs with short/non-alpha tokens
        # (equation fragments) and citation forms ("et al.").
        low = {t.text.lower() for t in tokens}
        if low & {"et", "al", "al."}:
            return True
        if sum(1 for t in tokens if t.pos_ == "PROPN") >= 2:
            return True
        if any(not t.is_alpha or len(t.text) < 3 for t in tokens):
            return True
        return False

    runs: list[list] = []
    run: list = []
    for tok in list(doc) + [None]:
        if tok is not None and tok.pos_ in {"NOUN", "PROPN"} \
                and not tok.is_space:
            run.append(tok)
            continue
        if len(run) >= 4 and not is_citation_like(run):
            runs.append(run)
        run = []
    # A stack the paper repeats is its term of art ("software engineering
    # payroll share", 150 times in one converted manuscript, P33): say so
    # once, where it first appears, not at every use.
    uses: dict[tuple, list] = {}
    for r in runs:
        uses.setdefault(tuple(t.lemma_.lower() for t in r), []).append(r)
    for same in uses.values():
        r = same[0]
        more = (f" (used {len(same)} times: if it is your term for one "
                "thing, define it once and keep it)") if len(same) > 1 else ""
        yield Suggestion(
            message="Insert a preposition or split the stack." + more,
            start=r[0].idx, end=r[-1].idx + len(r[-1].text))


# ---------------------------------------------------------------------------
# C301 — hedge stacking
# ---------------------------------------------------------------------------

_CLAUSE = frozenset({"ccomp", "xcomp", "advcl", "relcl", "acl", "csubj"})


def _in_complement_of(tok, verb) -> bool:
    """Is `tok` inside a clause subordinate to `verb`? True when a clause
    boundary (a ccomp, xcomp, relcl, ...) lies on the path from `tok` up
    to `verb`; False if `verb` is not an ancestor at all."""
    # spaCy hands out a fresh Token view on every access, so identity
    # (`is`) never matches: compare positions.
    crossed = tok.dep_ in _CLAUSE
    for anc in tok.ancestors:
        if anc.i == verb.i:
            return crossed
        if anc.dep_ in _CLAUSE:
            crossed = True
    return False


@rule("C301", "hedge-stack", Category.IMPROVEMENT,
      "Stacked hedges ('may possibly suggest') — one calibrated qualifier is stronger.",
      'Qualifiers are strength, not weakness: a well-placed hedge reads '
      "as command of the evidence. But stacking them ('it might possibly "
      "be tentatively suggested') is a calibration failure in the other "
      'direction: you talk yourself out of your own result. Pick the one '
      'hedge that matches the evidence and delete the rest.',
      plain=("You have used two cautious words close together, such as 'may "
             "possibly'. One is enough. Two make you sound unsure of your own "
             'result. Keep the one that fits your evidence.'),
      source="§4")
def c301_hedge_stack(doc, document: Document):
    # Dogfooding tunes: (1) "suggests that X may…" spreads one hedge over a
    # reporting verb and its complement clause — conventional, accepted
    # scientific phrasing, not a stack; we skip pairs separated by a clause
    # boundary ('that'/'which'/'whether'). (2) "could not possibly" is a
    # negation idiom, not a hedge stack. (3) Window tightened to 4.
    WINDOW = 4
    BOUNDARY = {"that", "which", "whether", "if", "and", "or", "but"}
    for sent in doc.sents:
        hedges = [t for t in sent if t.text.lower() in lx.HEDGE_TOKENS]
        flagged: set[int] = set()
        for a, b in zip(hedges, hedges[1:]):
            if b.i - a.i > WINDOW or a.i in flagged:
                continue
            between = sent.doc[a.i + 1:b.i]
            if any(t.lower_ in BOUNDARY for t in between):
                continue
            if any(t.lower_ in {"not", "n't", "never"}
                   for t in sent.doc[max(a.i - 2, 0):b.i]):
                continue
            # "suggests transition support could cost": "that" left out.
            # The second hedge sits in the clause the reporting verb
            # introduces, so it is the same hedge spread over two words,
            # exactly as "suggests that ... could" above (P35).
            if a.pos_ in ("VERB", "AUX") and _in_complement_of(b, a):
                continue
            yield Suggestion(
                message=f"'{a.text} … {b.text}' — keep one.",
                start=a.idx, end=b.idx + len(b.text))
            flagged.update({a.i, b.i})


# ---------------------------------------------------------------------------
# C303 — causal-language design check
# ---------------------------------------------------------------------------

# Verbs that also describe a change with no cause in view: "cases
# increased", "antibody levels decreased after a year". Only the
# transitive or passive use ("X increased Y", "Y was reduced by X") makes
# a causal claim (P31: these were C303's main misfire on the theses).
CHANGE_VERBS = {"increase", "decrease", "improve", "worsen", "lower",
                "raise", "reduce"}


def _has_object(tok) -> bool:
    deps = {c.dep_ for c in tok.children}
    if deps & {"dobj", "obj", "nsubjpass", "auxpass", "agent"}:
        return True
    # The small parser reads "Vaccination reduced transmission." as a
    # subject plus "reduced" modifying "transmission": the noun it
    # modifies is really its object.
    return tok.dep_ == "amod" and bool(deps & SUBJECT_DEPS)


@rule("C303", "causal-verb", Category.CONVENTION,
      "Causal verb — check the study design supports a causal claim.",
      "'Reduced', 'increased', 'prevented' assert causation. From a "
      'randomized or well-identified design, that is exactly right; from '
      "an observational or purely model-based result, 'was associated "
      "with', 'is consistent with', or 'the model implies' keeps the "
      'claim inside the evidence. This is a prompt, not a verdict: you '
      "know your design. Also keep 'the model implies X' distinct from "
      "'the world will do X'.",
      plain=('This verb says one thing caused another. That is right if your '
             'study design can show cause, such as a randomised trial. If your '
             "data are observational or from a model, 'was associated with' or "
             "'the model implies' is safer. You know your design; this is only a "
             'reminder.'),
      sections_only=("abstract", "results", "discussion", "conclusion",
                     "limitations"),
      source="§9.4")
def c303_causal(doc, document: Document):
    # Dogfooding tunes (this was the noisiest convention rule, 491 flags on
    # 8 theses):
    # 1. Purpose infinitives ("to prevent transmission") state an aim, not a
    #    causal finding — skipped.
    # 2. A modal ("might lead to") or a reporting/modelling frame
    #    ("we estimated that X averted Y") means the author has already
    #    calibrated the claim — skipped.
    # 3. Remaining hits are AGGREGATED: one suggestion per verb per section
    #    with a count, instead of one flag per occurrence. The prompt is
    #    pedagogical; firing it 40 times per chapter is fatigue, not
    #    pedagogy.
    MODALS = {"may", "might", "could", "would", "can"}
    FRAMES = {"estimate", "suggest", "indicate", "predict", "project",
              "simulate", "model", "assume", "expect", "imply",
              "hypothesize", "hypothesise"}

    def is_calibrated(tok) -> bool:
        if any(c.lemma_.lower() in MODALS for c in tok.children
               if c.dep_ in {"aux", "auxpass"}):
            return True
        return any(a.lemma_.lower() in FRAMES for a in tok.ancestors)

    hits: dict[tuple, list] = {}

    for tok in doc:
        if tok.pos_ != "VERB" or tok.lemma_.lower() not in lx.CAUSAL_VERB_LEMMAS:
            continue
        subjects = [c for c in tok.children if c.dep_ in SUBJECT_DEPS]
        if subjects and subjects[0].lemma_.lower() in lx.AUTHOR_SUBJECTS:
            continue  # "we increased the sample size" — author action
        if tok.i > 0 and doc[tok.i - 1].lower_ == "to":
            continue  # purpose infinitive
        if is_calibrated(tok):
            continue
        if tok.lemma_.lower() in CHANGE_VERBS and not _has_object(tok):
            continue  # "cases increased": a change described, not caused
        key = (tok.lemma_.lower(), document.section_at(tok.idx))
        hits.setdefault(key, []).append(
            (tok.idx, tok.idx + len(tok.text), tok.text))

    for pat in lx.CAUSAL_PHRASES:
        for m in re.finditer(pat, document.masked, re.IGNORECASE):
            # cheap modal guard for phrases: look back a few words
            back = document.masked[max(0, m.start() - 30):m.start()].lower()
            if re.search(r"\b(may|might|could|would|can|to)\s+$", back):
                continue
            key = ("lead-to", document.section_at(m.start()))
            hits.setdefault(key, []).append(
                (m.start(), m.end(), m.group(0)))

    for (lemma, _section), occ in hits.items():
        start, end, text = occ[0]
        extra = (f" ({len(occ)} uses of '{lemma}' in this section)"
                 if len(occ) > 1 else "")
        yield Suggestion(
            message=f"'{text}' asserts causation — supported by the design, "
                    f"or better as an association?{extra}",
            start=start, end=end)


# ---------------------------------------------------------------------------
# E7xx (syntax) — from the owner's lecture notes on scientific writing
# ---------------------------------------------------------------------------

@rule("E702", "adversative-run", Category.IMPROVEMENT,
      "Consecutive sentences opening with However/Nevertheless — whiplash.",
      'Use conjunctions deliberately, and adversatives sparingly. Each '
      "'However' reverses direction; two in quick succession leave the "
      'reader unsure which way the argument points. Fold one contrast '
      "into an 'although' clause, or restructure so a single turn carries "
      'it.',
      plain=("Two sentences in a row start with 'However' or a similar word. "
             'Each one turns the argument around, so the reader loses track of '
             'which way it is going. Join one contrast into the other sentence, '
             'or remove one.'),
      source="lecture")
def e702_adversative_run(doc, document: Document):
    ADV = re.compile(r"^\s*(However|Nevertheless|Nonetheless|Yet|"
                     r"On the other hand|Conversely)\b[, ]", re.IGNORECASE)
    recent: list[int] = []          # sentence indices with adversative opener
    for i, sent in enumerate(doc.sents):
        m = ADV.match(sent.text)
        if not m:
            continue
        if any(i - j <= 2 for j in recent):
            start = sent.start_char + m.start(1)
            yield Suggestion(
                message="Second adversative opener within three sentences — "
                        "merge the contrast or vary the structure.",
                start=start, end=start + len(m.group(1)))
        recent.append(i)


@rule("E703", "naked-this", Category.IMPROVEMENT,
      "Sentence-initial 'This' with no noun — what does it refer to?",
      'This, that, it and which are a common source of ambiguity: after a '
      'long sentence several referents are possible, and the writer, who '
      "knows the intended one, does not notice the gap. Give 'This' a "
      "noun ('This assumption', 'This discrepancy', 'This 3-fold "
      "difference') and the reference becomes checkable.",
      plain=("This sentence starts with 'This' on its own, and it is not clear "
             "what 'This' refers to. Add a noun: 'This assumption', 'This "
             "difference', 'This result'. Then the reader knows exactly what you "
             'mean.'),
      source="lecture")
def e703_naked_this(doc, document: Document):
    # Precision guard (the lecture's own caveat): the reference is ambiguous when
    # the PRECEDING sentence is long enough to offer multiple candidate
    # referents. After a short simple sentence, "This suggests…" is usually
    # clear — we stay quiet there.
    PREV_MIN_WORDS = 18
    prev_len = 0
    for sent in doc.sents:
        toks = [t for t in sent if not t.is_space and not t.is_punct]
        if len(toks) < 3:
            prev_len = len(toks)
            continue
        first, second = toks[0], toks[1]
        if (first.text == "This"
                and second.text.lower() in lx.NAKED_THIS_VERBS
                and second.pos_ in {"AUX", "VERB"}
                and prev_len >= PREV_MIN_WORDS):
            yield Suggestion(
                message="Name the referent: 'This finding/assumption/"
                        "pattern…' — the previous sentence offers several "
                        "candidates.",
                start=first.idx, end=second.idx + len(second.text))
        prev_len = len(toks)


@rule("E707", "display-first-opener", Category.IMPROVEMENT,
      "'Figure 1 shows…' — lead with the finding, cite the figure after.",
      'Results should keep a narrative: rather than opening with what a '
      "display shows ('Figure 2 shows the weekly incidence'), state what "
      "the results mean and cite the display at the end ('Weekly "
      "incidence peaked in July in every district (Figure 2).'). The "
      'reader gets the finding in the topic position and the pointer in '
      'parentheses.',
      plain=("This sentence starts with 'Figure 1 shows'. Start with the finding "
             "instead, and put the figure in brackets at the end: 'Cases peaked "
             "in July (Figure 1).' The reader gets the result first."),
      sections_only=("results",),
      source="lecture", aggregate=True)
def e707_display_first(doc, document: Document):
    for sent in doc.sents:
        m = re.match(lx.FIGURE_OPENER_RX, sent.text)
        if m:
            start = sent.start_char + m.start()
            yield Suggestion(
                message="Open with the result; move the display citation "
                        "into parentheses at the end.",
                start=start, end=start + len(m.group(0)))
