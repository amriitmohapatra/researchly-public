"""Fire / don't-fire tests for the rules mined from the owner's course and
lecture notes, Shehzad 2008 and Pallas 2022 (provenance in the private
knowledge base)."""

import spacy

from researchly.document import Document
from researchly.engine import check

NLP = spacy.load("en_core_web_sm")


def ids(text, kind="plain"):
    doc = Document.from_text(text, kind)
    return [s.rule_id for s in check(doc, NLP, show_preferences=True)]


# --- E701 empty phrases -----------------------------------------------------

def test_e701_fires_on_empty_value_phrase():
    assert "E701" in ids("This study sheds light on the transmission of "
                         "dengue in cities.")


def test_e701_quiet_on_concrete_statement():
    assert "E701" not in ids("This study estimates that school holidays "
                             "halve the daily contact rate of children.")


# --- E702 adversative runs --------------------------------------------------

def test_e702_fires_on_consecutive_howevers():
    t = ("Serological surveys are expensive. However, they detect "
         "infections that case reporting misses. However, assay "
         "cross-reactivity can inflate the estimates.")
    assert "E702" in ids(t)


def test_e702_quiet_on_single_however():
    t = ("Serological surveys are expensive. However, they detect "
         "infections that case reporting misses. Careful assay validation "
         "limits cross-reactivity.")
    assert "E702" not in ids(t)


# --- E703 naked this --------------------------------------------------------

def test_e703_fires_on_naked_this():
    # long preceding sentence = multiple candidate referents (the lecture's caveat)
    t = ("Hospital admissions in the northern districts rose for six "
         "consecutive weeks while testing capacity stayed flat and the "
         "share of positive tests doubled across every age group. "
         "This suggests that case counts understated the epidemic.")
    assert "E703" in ids(t)


def test_e703_quiet_when_this_has_a_noun():
    t = ("Hospital admissions in the northern districts rose for six "
         "consecutive weeks while testing capacity stayed flat and the "
         "share of positive tests doubled across every age group. "
         "This divergence suggests that case counts understated the "
         "epidemic.")
    assert "E703" not in ids(t)


def test_e703_quiet_after_short_clear_sentence():
    # after a short simple sentence the referent is unambiguous — stay quiet
    t = "Admissions rose sharply. This suggests the wave was underway."
    assert "E703" not in ids(t)


# --- E704 uncited consensus -------------------------------------------------

def test_e704_fires_without_citation():
    assert "E704" in ids("Seasonal forcing is considered to be the main "
                         "driver of the winter peak.")


def test_e704_quiet_with_citation():
    assert "E704" not in ids("Seasonal forcing is considered to be the main "
                             "driver of the winter peak (Smith et al, "
                             "2019).")


# --- E705 absolute novelty --------------------------------------------------

def test_e705_fires_on_bare_novelty_claim():
    assert "E705" in ids("Income-related contact heterogeneity has not been "
                         "studied in Southeast Asia.")


def test_e705_quiet_with_softener():
    assert "E705" not in ids("To our knowledge, income-related contact "
                             "heterogeneity has not been studied in "
                             "Southeast Asia.")


# --- E706 relatively --------------------------------------------------------

def test_e706_fires():
    assert "E706" in ids("Attack rates were relatively high in the lowest "
                         "quintile.")


# --- E707 display-first openers ---------------------------------------------

def test_e707_fires_in_results():
    t = "Results\n\nFigure 2 presents the weekly case counts by district."
    assert "E707" in ids(t)


def test_e707_quiet_when_finding_leads():
    t = ("Results\n\nWeekly case counts peaked in July in every district "
         "(Figure 2).")
    assert "E707" not in ids(t)


def test_e707_quiet_outside_results():
    t = "Methods\n\nFigure 1 shows the model structure."
    assert "E707" not in ids(t)


# --- AB801 vague abstract forward references --------------------------------

def test_ab801_fires_in_abstract():
    t = ("Abstract\n\nWe fitted an SEIR model to case data. Results will "
         "be discussed in the context of vaccination policy.")
    assert "AB801" in ids(t)


def test_ab801_quiet_when_results_stated():
    t = ("Abstract\n\nWe fitted an SEIR model to case data. Vaccination "
         "reduced hospitalisations by 34% in all scenarios.")
    assert "AB801" not in ids(t)


# --- L901 serial-summary openers --------------------------------------------

def test_l901_fires_on_catalogue_opener():
    assert "L901" in ids("There are many studies examining how rainfall "
                         "affects mosquito abundance.")


def test_l901_quiet_on_synthesis_opener():
    assert "L901" not in ids("Evidence consistently links poor sleep with "
                             "worse metabolic outcomes.")


# --- D902 missing niche signal ----------------------------------------------

_INTRO_NO_GAP = (
    "Introduction\n\n" + ("Dengue is a mosquito-borne viral disease with "
    "rising global incidence. Transmission is seasonal in many settings. "
    "Vector control has been the mainstay of prevention for decades. "
    "Vaccines have recently become available in several countries. ") * 4
    + "\n\nMethods\n\nWe fitted a model."
)

_INTRO_WITH_GAP = _INTRO_NO_GAP.replace(
    "Methods\n\nWe fitted a model.",
    "However, the contribution of income-related contact heterogeneity "
    "remains unquantified in Southeast Asian settings.\n\n"
    "Methods\n\nWe fitted a model.")


def test_d902_fires_when_intro_lacks_gap():
    assert "D902" in ids(_INTRO_NO_GAP)


def test_d902_quiet_when_gap_present():
    assert "D902" not in ids(_INTRO_WITH_GAP)


def test_d902_quiet_without_intro_section():
    assert "D902" not in ids("Results\n\nAttack rates rose sharply in the "
                             "lowest quintile of income.")


# --- W201 additions from the lecture's avoid-list ---------------------------

def test_w201_leverage_and_elucidate():
    found = ids("We leveraged survey data to elucidate contact patterns.")
    assert found.count("W201") == 2
