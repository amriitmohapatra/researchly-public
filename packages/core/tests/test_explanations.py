"""Every suggestion explains itself in everyday words, and nothing a user
sees refers to this repository's internals (P35, from the owner's first
real use: "the user may not know what Guide 4.2 is").

Also the three precision fixes from the same feedback: Latin phrases in the
spelling tier, a hedge inside the clause a reporting verb introduces, and
the new equation-in-a-sentence rule. Synthetic text only.
"""

import re
from pathlib import Path

import pytest

from researchly import api, sources
from researchly.document import Document
from researchly.engine import REGISTRY, load_rules

NLP = api.get_nlp()

# What must never reach a card: section numbers of the internal guide,
# course codes, lecturer names, book citations that belong on the Source
# line, command-line instructions, and code formatting.
# Course codes are caught by shape; the lecturer's and course's names are
# private and live only in the private repository's terms list, which this
# test reads when it is there (the public copy has no such file).
_TERMS = Path(__file__).resolve().parents[3] / "tools" / "public-export" / "private-terms.txt"
PRIVATE = [ln.strip() for ln in (_TERMS.read_text("utf-8").splitlines() if _TERMS.exists() else [])
           if ln.strip() and not ln.lstrip().startswith("#")]
INTERNAL = re.compile(
    r"§|`|\b[A-Z]{2,3} ?\d{4}\b|\bGuide\b|Belcher|Pallas|Shehzad|Swales|Gopen|"
    r"researchly (?:abstract|review|check|dict)|pip install"
    + "".join("|(?i:%s)" % t for t in PRIVATE))


def hits(text: str, rule_id: str, kind: str = "plain"):
    doc = Document.from_text(text, kind)
    return [s for s in api.analyze(doc, nlp=NLP,
                                   show_preferences=True).suggestions
            if s.rule_id == rule_id]


# --- every rule has a plain explanation, free of internal references ----------------

def test_every_rule_has_a_plain_explanation():
    load_rules()
    missing = [r.id for r in REGISTRY.values() if len(r.plain.split()) < 8]
    assert missing == []


@pytest.mark.parametrize("field", ["short", "why", "plain"])
def test_no_internal_references_reach_the_user(field):
    load_rules()
    bad = {r.id: getattr(r, field) for r in REGISTRY.values()
           if INTERNAL.search(getattr(r, field))}
    assert bad == {}


def test_suggestions_carry_the_plain_text():
    (h,) = hits("Methods\n\nWe fitted the the model.\n", "W207")
    assert h.plain == REGISTRY["W207"].plain
    assert "plain" in h.to_dict()


# --- sources: training materials are credited as the owner's learnings ------------

def test_course_and_lecture_rules_cite_the_owners_learnings():
    load_rules()
    for rid in ("E703", "L901", "AB801"):
        assert REGISTRY[rid].source == sources.LEARNINGS
    assert not INTERNAL.search(sources.LEARNINGS)


def test_combined_source_codes_do_not_repeat_a_citation():
    assert sources.cite("lecture+course-U1") == sources.LEARNINGS
    assert sources.cite("§6+lecture").count(sources.LEARNINGS) == 1


# --- S001: Latin phrases --------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Results\n\nSix states had a 100% ad valorem excise in 2016.\n",
    "Methods\n\nIncome per capita was measured ex ante and de facto.\n",
    "Methods\n\nThe assays were run in vitro and in silico.\n",
])
def test_latin_phrases_are_not_typos(text):
    assert hits(text, "S001") == []


def test_a_latin_word_alone_is_still_checked():
    # "valorem" without "ad" is not a phrase; a typo of "valour" perhaps
    (h,) = hits("Results\n\nThe valorem of the tax rose.\n", "S001")
    assert h.text == "valorem"


# --- C301: a hedge in the clause a reporting verb introduces ------------------------

@pytest.mark.parametrize("text", [
    # "that" left out: the same as "suggests that ... could"
    "Results\n\nOne scenario suggests transition support could cost under "
    "2% of the gain.\n",
    "Results\n\nThe data suggest incidence may fall by half.\n",
    "Results\n\nThe fit indicates the peak might come later.\n",
])
def test_hedge_across_an_unmarked_clause_is_not_a_stack(text):
    assert hits(text, "C301") == []


@pytest.mark.parametrize("text", [
    "Results\n\nThis may possibly reflect reporting delays.\n",
    "Results\n\nIt seems likely that the cases could rise.\n",
])
def test_true_hedge_stacks_still_fire(text):
    assert len(hits(text, "C301")) == 1


# --- X302: an equation that is not part of a sentence --------------------------------

def tex(body: str) -> str:
    return ("\\documentclass{article}\\begin{document}\\section{Methods}\n"
            + body + "\n\\end{document}\n")


def test_x302_fires_on_an_equation_after_a_full_stop():
    doc = tex("We assume mass action.\n\\begin{equation}\\lambda = \\beta I / N"
              "\\end{equation}\nwhere N is the population.")
    (h,) = hits(doc, "X302", "latex")
    assert "full stop" in h.message and h.category.value == "convention"


@pytest.mark.parametrize("body", [
    # led in: the equation is the sentence's object
    "The force of infection is\n\\begin{equation}\\lambda = \\beta I / N"
    "\\end{equation}\nwhere N is the population.",
    # a colon is a lead-in
    "The force of infection is given by:\n\\[\\lambda = \\beta I / N\\]",
    # an abbreviation's full stop
    "The rate is as in earlier work, e.g.\n\\begin{equation}r = 2"
    "\\end{equation}",
    # a sentence-ending citation is masked: "as shown by \\cite{x}." still
    # ends the sentence, but the next equation here is led in
    "As shown by \\cite{zq}. The rate is\n\\begin{equation}r = 2\\end{equation}",
    # the first thing in the section
    "\\begin{equation}r = 2\\end{equation}\nis the rate.",
])
def test_x302_quiet(body):
    assert hits(tex(body), "X302", "latex") == []


def test_x302_does_not_run_on_plain_text():
    assert hits("Methods\n\nWe assume mass action.\n\nr = 2\n", "X302") == []


# Word: the add-in sends paragraph text, so an equation object arrives in
# its linear form; an uploaded .docx records the object itself (below).

def word(*paras):
    doc = Document.from_word(
        [{"text": "Methods", "style": "Heading 1"}]
        + [p if isinstance(p, dict) else {"text": p} for p in paras])
    return [s for s in api.analyze(doc, nlp=NLP,
                                   show_preferences=True).suggestions
            if s.rule_id == "X302"]


def test_x302_fires_on_a_word_equation_paragraph_after_a_full_stop():
    (h,) = word("We assume mass action.", "λ = βI/N",
                "where N is the population.")
    assert h.text == "action."


@pytest.mark.parametrize("paras", [
    # led in
    ("The force of infection is", "λ = βI/N\t(1)", "where N is the population."),
    # a colon is a lead-in
    ("The force of infection is given by:", "R0 = β/γ"),
    # an abbreviation's full stop
    ("The rate is as in earlier work, e.g.", "r = 2"),
    # an equation inside a sentence's paragraph is inline, not displayed
    ("We assume mass action.", "Let x = 2 be the rate of growth."),
    # a paragraph of words with an equals sign is prose
    ("We assume mass action.", "Here the growth rate = births minus deaths."),
    # a table cell is never a displayed equation
    ("We assume mass action.", {"text": "N = 1,234", "kind": "table"}),
])
def test_x302_quiet_in_word(paras):
    assert word(*paras) == []


def test_x302_sees_a_flattened_pdf_equation():
    # a PDF conversion flattens a displayed equation to symbols (P33)
    (h,) = word("We assume mass action.",
                "d log y j t = (1 − ε)d log c j t + d log x t")
    assert h.text == "action."
