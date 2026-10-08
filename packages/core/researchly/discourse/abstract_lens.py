"""The abstract lens — Belcher/Pallas six-part completeness check.

From the owner's course materials (Belcher 2021; Pallas 2022 ch.7): a good
SciQua abstract contains six moves —

  1. background      — the conventional wisdom on the topic
  2. gap             — problematization: what's missing/unresolved
  3. aim             — the research question or objective
  4. methods         — how the question is answered
  5. findings        — what was found (with substance, not promises)
  6. significance    — what it means for the field / practice

This lens detects each move by signal lexicons and reports what's missing:
as a single aggregate rule (AB802) on abstracts, and in full detail via
`researchly abstract`, which offers a fill-in sentence frame for each
missing move. Deterministic and explainable, like everything else.

The frames below are Researchly's own wording. The idea of giving the
writer one fill-in frame per move is Pallas's (2022, ch. 7); her frames
are not reproduced (all rights reserved — see PLAN.md S0).
"""

from __future__ import annotations

import re

from ..document import Document
from ..engine import Category, Suggestion, rule

MOVES = ("background", "gap", "aim", "methods", "findings", "significance")

SIGNALS: dict[str, list[str]] = {
    "gap": [
        r"\bhowever\b", r"\balthough\b", r"\byet\b", r"\bnevertheless\b",
        r"\bremains? (unclear|unknown|unexplored|unquantified|limited|"
        r"uncertain|to be)\b",
        r"\b(has|have) (not|never|yet to)\b", r"\blittle is known\b",
        r"\bfew(er)? studies\b", r"\blimited (evidence|research|data|"
        r"understanding|insight)\b", r"\bgap\b", r"\bpaucity\b",
        r"\bunderstudied\b", r"\boverlooked\b",
        r"\bhas yet to (explain|address|examine|quantify)\b",
        r"\bpropensity to\b.*\bchallenge\b", r"\bconcern\b",
    ],
    "aim": [
        r"\bwe (ask|asked|aim|aimed|sought|set out|investigate|investigated|"
        r"examine|examined|assess|assessed|evaluate|evaluated|explore|"
        r"explored|quantify|quantified|characteri[sz]ed?|test|tested|"
        r"hypothesi[sz]ed?|study|studied|expand)\b",
        r"\bthis (paper|study|thesis|dissertation|work) (asks|aims|"
        r"investigates|examines|assesses|evaluates|explores|quantifies|"
        r"addresses|seeks|expands|proposes)\b",
        r"\b(our|the) (objective|aim|goal|purpose)s? (of this study )?"
        r"(was|were|is|are)\b",
        r"\bthe aims? of this (study|paper|thesis)\b",
        r"\bresearch question\b", r"\bhere,? we\b",
        r"\bto (address|answer|fill|investigate|determine|understand) "
        r"(this|these|whether|the)\b",
    ],
    "methods": [
        r"\bwe (used|use|fitted|fit|conducted|developed|applied|analy[sz]ed|"
        r"model(led|ed)|simulated|estimated|recruited|collected|compared|"
        r"combined|shortlisted|graded|surveyed|interviewed|reviewed|"
        r"screened|extracted|calibrated|implemented)\b",
        r"\busing (a|an|the|data|survey|model|regression|bayesian|"
        r"interviews?|case stud)\b",
        r"\bdata (from|were|was)\b", r"\bwere (recruited|collected|included|"
        r"enrolled|analy[sz]ed|extracted|graded|randomi[sz]ed)\b",
        r"\b(cohort|cross-sectional|randomi[sz]ed|case-control|"
        r"longitudinal|retrospective|prospective) (study|trial|design|"
        r"survey|analysis)\b",
        r"\b(seir|sir|compartmental|branching process|regression|"
        r"agent-based) model\b",
    ],
    "findings": [
        r"\bwe (found|find|observed|identified|estimate[d]? that|show|"
        r"showed|demonstrate[d]?|report)\b",
        r"\bresults? (show|showed|indicate[d]?|reveal(ed)?|suggest(ed)?)\b",
        r"\bwas (significantly )?(associated|correlated|linked)\b",
        r"\b(higher|lower|greater|increased|decreased|reduced) "
        r"(than|by|among|in)\b",
        r"\b\d+(\.\d+)?\s?%", r"\b95\s?% (ci|cri|credible|confidence)\b",
        r"\b(odds|risk|hazard|rate) ratio\b",
        r"\bscored? (significantly )?(higher|lower)\b",
        r"\bcompared (with|to)\b.*\b\d",
    ],
    "significance": [
        r"\bthese (findings|results|data) (suggest|indicate|imply|"
        r"highlight|underscore|demonstrate|reinforce|point)\b",
        r"\bour (study|findings|results) (demonstrates?|suggests?|"
        r"highlights?|provides?|underscores?)\b",
        r"\bimplications?\b", r"\binform(ing|s)? (policy|practice|"
        r"decision|planning|control|surveillance|guidelines)\b",
        r"\bfuture (research|studies|work)\b",
        r"\b(clinicians|policymakers|public health|practitioners|"
        r"researchers) (could|can|should|may|need)\b",
        r"\bpotential (role|use|application|value)\b",
        r"\bcontribut(es?|ion) to\b",
        r"\bmust (change|adapt|reconsider)\b",
    ],
}

# Fill-in frames, one per move (structure after Pallas 2022, ch. 7; the
# wording is original to Researchly).
FRAMES = {
    "background": "“Studies of [topic] generally find that [current "
                  "consensus]…”",
    "gap": "“Yet [that account] cannot explain [observation], because "
           "[reason].” or “What remains unclear is [specific unknown].”",
    "aim": "“We therefore set out to determine [research question].”",
    "methods": "“We [fitted/analysed/surveyed] [model, design or data] "
               "from [setting, period]…”",
    "findings": "“[Main outcome] was [value, with uncertainty] in [group], "
                "compared with [comparator].”",
    "significance": "“This means that [field/practice] should [specific "
                    "change]…” or “[Decision-makers] could use this to "
                    "[action].”",
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def analyze(text: str) -> dict:
    """Return {move: {"present": bool, "evidence": str|None}}."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text.strip())
                 if s.strip()]
    result: dict = {}

    def find(move: str):
        for sent in sentences:
            for rx in SIGNALS[move]:
                if re.search(rx, sent, re.IGNORECASE):
                    return sent
        return None

    for move in ("gap", "aim", "methods", "findings", "significance"):
        ev = find(move)
        result[move] = {"present": ev is not None,
                        "evidence": (ev[:160] if ev else None)}

    # Background: the opening should set the scene, not jump straight into
    # "we did X". Present when the first sentence is not already an
    # aim/methods sentence.
    first = sentences[0] if sentences else ""
    opens_cold = any(
        re.search(rx, first, re.IGNORECASE)
        for rx in SIGNALS["aim"] + SIGNALS["methods"])
    result["background"] = {
        "present": bool(first) and not opens_cold,
        "evidence": first[:160] if first and not opens_cold else None,
    }
    return {m: result[m] for m in MOVES}


def missing_moves(text: str) -> list[str]:
    a = analyze(text)
    return [m for m in MOVES if not a[m]["present"]]


@rule("AB802", "abstract-completeness", Category.IMPROVEMENT,
      "Abstract is missing one of its six moves (background, gap, question, methods, findings, significance).",
      'A strong abstract compresses the whole paper into six moves: '
      'background (conventional wisdom), gap (problematization), research '
      'question, methods, findings and significance. Reviewers scan for '
      'exactly these; a missing move reads as a missing part of the '
      'argument. The card names the moves it could not find.',
      plain=('A good abstract answers six things in order: what is known, what '
             'is missing, what you asked, how you did it, what you found, and '
             'why it matters. One of these is missing here. Reviewers look for '
             'all six.'),
      sections_only=("abstract",),
      source="course-U2",
      scope="document")
def ab802_abstract_completeness(doc, document: Document):
    abstracts = [h for h in document.headings if h.section == "abstract"]
    if abstracts:
        start = abstracts[0].start
        # The section runs to the next heading of another section; its
        # own subsections ("Background", "Aims") are part of it.
        ends = [h.start for h in document.headings
                if h.start > start and h.section != "abstract"]
        end = min(ends) if ends else len(document.masked)
    elif document.default_section == "abstract" and not document.headings:
        start, end = 0, len(document.masked)      # the "abstract" profile
    else:
        return
    text = document.masked[start:end].strip()
    if len(text) < 300:                     # stubs can't be judged
        return
    missing = missing_moves(text)
    if not missing:
        return
    # Highlight the abstract's first sentence. The heading's own text is not
    # always at `start`: a LaTeX abstract environment has no title in the
    # source, so `start + len("Abstract")` landed on "\\begin{a" (P29).
    body = document.masked[start:end]
    first = start + len(body) - len(body.lstrip())
    stop = re.search(r"[.!?](\s|$)", document.masked[first:end])
    last = first + (stop.end() if stop else min(len(body.strip()), 200))
    yield Suggestion(
        message=("Missing move" + ("s" if len(missing) > 1 else "")
                 + ": " + ", ".join(missing)
                 + ". Six-part check: background → gap → question → "
                   "methods → findings → significance."),
        start=first, end=last)
