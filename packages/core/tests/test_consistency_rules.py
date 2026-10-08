"""S2b consistency checks: abbreviations, numbers and units, compounds.

Synthetic sentences only. Each don't-fire case is a pattern the thesis
corpus or the real-document bench produced (P32).
"""

import pytest

from researchly import api
from researchly.document import Document
from researchly.rules_consistency import _long_form

NLP = api.get_nlp()


def hits(text: str, rule_id: str, kind: str = "plain"):
    doc = Document.from_text(text, kind)
    return [s for s in api.analyze(doc, nlp=NLP,
                                   show_preferences=True).suggestions
            if s.rule_id == rule_id]


# --- definitions (Schwartz & Hearst) ----------------------------------------------

@pytest.mark.parametrize("short,before,expected", [
    ("STAR", "we fitted the space-time autoregressive",
     "space-time autoregressive"),
    ("DALY", "the burden in Disability Adjusted Life Years",
     "Disability Adjusted Life Year"),
    ("H1N1", "influenza A", None),                 # notation, A(H1N1)
    ("D-F", "modelled titres", None),               # panel letters
])
def test_long_form(short, before, expected):
    got = _long_form(short, before)
    assert (got is None) == (expected is None)
    if expected:
        assert got.startswith(expected[:12])


# --- F612: defined twice --------------------------------------------------------------

def test_f612_fires_on_a_second_definition():
    text = ("Methods\n\nWe fitted a space-time autoregressive (STAR) model. "
            "The STAR model used weekly counts and the STAR fit was good. "
            "Each space-time autoregressive (STAR) model had two lags.\n")
    (h,) = hits(text, "F612")
    assert "STAR" in h.message


@pytest.mark.parametrize("text", [
    # the abstract stands alone
    "Abstract\n\nWe used a space-time autoregressive (STAR) model.\n\n"
    "Methods\n\nWe fitted a space-time autoregressive (STAR) model to the "
    "STAR data.\n",
    # a new chapter's introduction may define it again
    "Methods\n\nWe used a space-time autoregressive (STAR) model.\n\n"
    "Introduction\n\nA space-time autoregressive (STAR) model is used.\n",
    # a caption defines its abbreviations again on purpose
    "Methods\n\nWe used a space-time autoregressive (STAR) model.\n\n"
    "Figure 2. Forecasts of the space-time autoregressive (STAR) model.\n",
    # notation, not a definition
    "Methods\n\nCases of influenza A(H1N1) and later A(H1N1) were seen.\n",
])
def test_f612_quiet(text):
    assert hits(text, "F612") == []


# --- F613: defined but barely used (Preference) ----------------------------------------

def test_f613_fires_and_is_a_preference():
    (h,) = hits("Methods\n\nWe used a latent class model (LCM) for the "
                "choices.\n", "F613")
    assert h.category.value == "preference"


def test_f613_quiet_when_used():
    assert hits("Methods\n\nWe used a latent class model (LCM). The LCM "
                "fitted well, and the LCM classes were stable.\n",
                "F613") == []


# --- N101: unit spacing mixed ----------------------------------------------------------

def test_n101_fires_on_the_minority_style():
    (h,) = hits("Results\n\nCoverage rose by 5%, then 7%, then 9 %, then "
                "12%.\n", "N101")
    assert h.text == "9 %"


@pytest.mark.parametrize("text", [
    "Results\n\nCoverage rose by 5%, then 7%, then 9%.\n",
    "Results\n\nCoverage rose by 5 %, then 7 %, then 9 %.\n",
    "Results\n\nThe sites were 2 km and 5 km apart; 10%, then 12%.\n",
])
def test_n101_quiet_when_consistent(text):
    assert hits(text, "N101") == []


# --- N102: sentence starts with a numeral --------------------------------------------

def test_n102_fires():
    (h,) = hits("Results\n\nThe survey ran in May. 17 districts reported "
                "cases in the first week.\n", "N102")
    assert h.text == "17"


@pytest.mark.parametrize("text", [
    "Results\n\nThe survey ran in May. 2019 was the worst season.\n",
    "Results\n\n1. Introduction of the vaccine in every district.\n",
    "Results\n\nThe survey ran in May. Seventeen districts reported cases.\n",
    "Results\n\nAge group 4.4 3.2 2.9 5.1 6.0 7.2 by district.\n",
])
def test_n102_quiet(text):
    assert hits(text, "N102") == []


# --- W211: compound spelled two ways --------------------------------------------------

def test_w211_fires_on_the_minority_spelling():
    (h,) = hits("Methods\n\nThe dataset was large. We split the dataset "
                "into folds. The data set had gaps.\n", "W211")
    assert h.text == "data set"


@pytest.mark.parametrize("text", [
    "Methods\n\nThe dataset was large. We split the dataset into folds.\n",
    # verb and noun: "set up" is not "setup" spelled open
    "Methods\n\nThe setup was simple; we set up the model in a day.\n",
    # a hyphenated number compound is not the open form
    "Methods\n\nOver a 28-day time window the daytime counts rose.\n",
    # not a word when run together
    "Methods\n\nA test negative design; the testnegative cases were few.\n",
])
def test_w211_quiet(text):
    assert hits(text, "W211") == []


@pytest.mark.parametrize("text", [
    # panel letters, not an abbreviation
    "Methods\n\nThe colour bar of the panel (A-C) is shared. Each "
    "panel (A-C) has its own scale.\n",
    # a definition inside a cited title belongs to the cited paper
    "Methods\n\nWe used a space-time autoregressive (STAR) model.\n\n"
    "Zqlee A, Zqtan B, et al. A space-time autoregressive (STAR) model "
    "for dengue. Lancet. 2020;12:1-9.\n",
])
def test_f612_quiet_on_panels_and_reference_entries(text):
    assert hits(text, "F612") == []


def test_w211_quiet_on_two_real_words():
    assert hits("Methods\n\nNotable cases were few. We were not able to "
                "trace them.\n", "W211") == []


def test_f612_quiet_in_a_latex_caption():
    src = ("\\documentclass{article}\\begin{document}\\section{Methods}\n"
           "We used a latent class model (LCM). The LCM fitted.\n"
           "\\begin{figure}\\caption{Classes of the latent class model "
           "(LCM) by age.}\\label{fig:a}\\end{figure}\n"
           "See Figure~\\ref{fig:a}.\n\\end{document}\n")
    assert hits(src, "F612", "latex") == []
