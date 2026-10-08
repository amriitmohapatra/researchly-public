"""Tests for the Belcher/Pallas six-part abstract lens."""

import spacy

from researchly.abstract_lens import MOVES, analyze, missing_moves
from researchly.document import Document
from researchly.engine import check

NLP = spacy.load("en_core_web_sm")

# A synthetic exemplar written for this suite. It follows the six-move
# structure of the worked example in Pallas (2022, ch. 7) — conventional
# wisdom, problematization, question, design, findings, significance — but
# none of her wording (her text is all-rights-reserved; see PLAN.md S0).
EXEMPLAR = (
    "Published reviews of school-based influenza vaccination agree that "
    "immunising children protects older members of their households. "
    "However, the size of this indirect benefit differs sharply between "
    "countries, and some programmes report almost no spillover to "
    "grandparents. The literature has not explained why the indirect "
    "effect is so variable. In this paper, we ask which features of "
    "household structure determine how much protection children pass on "
    "to older relatives. To answer this question, we build an "
    "age-structured transmission model and calibrate it to household "
    "survey data from Japan and Italy. We find that the share of "
    "three-generation households explains most of the difference in "
    "indirect protection between the two settings. These findings suggest "
    "that vaccination planners should weigh household composition when "
    "they forecast the benefit of school programmes."
)


def test_pallas_exemplar_has_all_six_moves():
    assert missing_moves(EXEMPLAR) == []
    a = analyze(EXEMPLAR)
    assert all(a[m]["present"] for m in MOVES)
    assert "Published reviews" in a["background"]["evidence"]
    assert "However" in a["gap"]["evidence"]
    assert "we ask" in a["aim"]["evidence"]
    assert "We find" in a["findings"]["evidence"]
    assert "These findings suggest" in a["significance"]["evidence"]


def test_methods_only_abstract_missing_five():
    t = ("We fitted an SEIR model to dengue case data from Singapore "
         "using Bayesian inference. Results will be discussed.")
    missing = missing_moves(t)
    assert "methods" not in missing
    assert {"background", "gap", "aim", "findings",
            "significance"} <= set(missing)


def test_cold_open_flags_missing_background():
    t = "We ask whether income shapes contact patterns. " + EXEMPLAR
    a = analyze(t)
    assert not a["background"]["present"]     # first sentence is the aim


def test_epi_flavoured_signals():
    t = ("Dengue burden is rising across Southeast Asia. However, the role "
         "of income-related contact heterogeneity remains unquantified. "
         "We aimed to quantify its contribution to transmission. Using a "
         "compartmental model fitted to surveillance data, we estimated "
         "attack rates by income quintile. Attack rates were 40% higher in "
         "the lowest quintile (95% CrI: 25-58%). These findings suggest "
         "that equity-aware vaccination strategies could inform policy.")
    assert missing_moves(t) == []


def test_ab802_rule_fires_on_incomplete_abstract():
    t = ("Abstract\n\n"
         "We fitted an SEIR model to dengue case data from Singapore using "
         "Bayesian inference implemented in Stan with weakly informative "
         "priors. We used surveillance data from 2013 to 2020 covering all "
         "reporting clinics, and we conducted extensive sensitivity "
         "analyses across model structures and prior choices to confirm "
         "robustness of the fitting procedure across seasons and regions.")
    doc = Document.from_text(t, "plain")
    hits = [s for s in check(doc, NLP, disabled={"LT001"},
                             show_preferences=False)
            if s.rule_id == "AB802"]
    assert len(hits) == 1
    assert "findings" in hits[0].message
    assert "significance" in hits[0].message


def test_ab802_quiet_on_complete_abstract():
    doc = Document.from_text("Abstract\n\n" + EXEMPLAR, "plain")
    hits = [s for s in check(doc, NLP, disabled={"LT001"},
                             show_preferences=False)
            if s.rule_id == "AB802"]
    assert hits == []


def test_ab802_quiet_without_abstract_section():
    doc = Document.from_text("Methods\n\nWe fitted a model to the data.",
                             "plain")
    hits = [s for s in check(doc, NLP, disabled={"LT001"},
                             show_preferences=False)
            if s.rule_id == "AB802"]
    assert hits == []
