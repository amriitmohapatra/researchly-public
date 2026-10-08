"""Fire / don't-fire tests for the v0.1 rule pack.

Philosophy: every rule gets at least one positive and one negative case.
The negative cases encode the *precision* promises (section-awareness,
technical-usage exemptions, masking) that differentiate Researchly from
genre-blind checkers.
"""

import pytest
import spacy

from researchly.document import Document
from researchly.engine import check

NLP = spacy.load("en_core_web_sm")


def ids(text, kind="plain", show_preferences=True):
    doc = Document.from_text(text, kind)
    return [s.rule_id for s in
            check(doc, NLP, show_preferences=show_preferences)]


def get(text, rule_id, kind="plain"):
    doc = Document.from_text(text, kind)
    return [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == rule_id]


# --- G101 subject–verb separation -----------------------------------------

def test_g101_fires_on_long_interruption():
    t = ("The model, which incorporates income quintiles, seasonal forcing, "
         "and age structure across all districts, predicts higher attack "
         "rates.")
    assert "G101" in ids(t)


def test_g101_quiet_on_short_sentence():
    assert "G101" not in ids("The model predicts higher attack rates.")


# --- G102 buried action ----------------------------------------------------

def test_g102_fires_on_light_verb_nominalization():
    t = "We performed an estimation of the transmission rate."
    out = get(t, "G102")
    assert out and out[0].replacement == "estimated"
    # applying the fix in place must be grammatical
    s = out[0]
    fixed = t[:s.start] + s.replacement + t[s.end:]
    assert fixed == "We estimated the transmission rate."


def test_g102_quiet_on_plain_verb():
    assert "G102" not in ids("We estimated the transmission rate.")


# --- G103 nominalization density -------------------------------------------

def test_g103_fires_on_dense_sentence():
    t = ("The estimation of parameters requires the harmonization of survey "
         "waves and the standardization of stratification procedures.")
    assert "G103" in ids(t)


def test_g103_allowlist_does_not_count():
    # population/distribution/incidence are standard technical vocabulary
    t = ("The population distribution of incidence varied by region and "
         "season across the study period.")
    assert "G103" not in ids(t)


# --- G104 passive with agent, section-aware --------------------------------

def test_g104_fires_outside_methods():
    t = "Results\n\nThe pattern was first described by Anderson and May."
    assert "G104" in ids(t)


def test_g104_silent_in_methods():
    t = "Methods\n\nThe pattern was first described by Anderson and May."
    assert "G104" not in ids(t)


def test_g104_quiet_on_agentless_passive():
    # agentless passive is often the right call; we stay quiet
    assert "G104" not in ids("Results\n\nSamples were incubated at 37 degrees.")


# --- G105 expletive opener --------------------------------------------------

def test_g105_fires():
    assert "G105" in ids("There are three factors that drive transmission.")


def test_g105_quiet():
    assert "G105" not in ids("Three factors drive transmission.")


# --- G106 overlong sentence -------------------------------------------------

def test_g106_fires():
    t = ("Because the survey instrument was administered in four languages "
         "and the sampling frame differed between urban and rural strata "
         "in ways that were difficult to anticipate before fieldwork began, "
         "and because interviewer effects were likely to vary across "
         "districts and seasons for reasons beyond our control, we adjusted "
         "all estimates for language, stratum, interviewer, and calendar "
         "month in a hierarchical model with weakly informative priors.")
    assert "G106" in ids(t)


def test_g106_quiet_below_50_words():
    t = ("Because the survey instrument was administered in four languages "
         "and the sampling frame differed between urban and rural strata, "
         "and because interviewer effects were likely to vary across "
         "districts and seasons, we adjusted all estimates for language, "
         "stratum, interviewer, and calendar month in a hierarchical model.")
    assert "G106" not in ids(t)


# --- G107 noun strings ------------------------------------------------------

def test_g107_fires():
    assert "G107" in ids(
        "We describe the income quintile contact matrix estimation procedure.")


def test_g107_quiet_on_short_compound():
    assert "G107" not in ids("We estimated the contact matrix directly.")


# --- G108 stress position ---------------------------------------------------

def test_g108_fires_on_trailing_attribution():
    assert "G108" in ids(
        "Attack rates rose sharply, according to our simulations.")


# --- W-rules ----------------------------------------------------------------

def test_w201_and_w202():
    found = ids("We utilize diaries in order to measure contacts.")
    assert "W201" in found and "W202" in found


def test_w203_hype_but_not_technical_novel():
    assert "W203" in ids("Our novel framework captures heterogeneity.")
    assert "W203" not in ids("The novel coronavirus emerged in 2019.")


def test_w205_filler():
    assert "W205" in ids(
        "It is important to note that estimates are preliminary.")


def test_w206_redundant_pair():
    assert "W206" in ids("This was true for each and every scenario.")


def test_w207_doubled_word():
    assert "W207" in ids("The results in the the table are final.")
    assert "W207" not in ids("The work he had had was finished.")


def test_w208_contraction():
    assert "W208" in ids("The model doesn't converge without reparameterization.")


def test_w204_preference_hidden_by_default():
    t = "The effect was very large."
    assert "W204" in ids(t, show_preferences=True)
    assert "W204" not in ids(t, show_preferences=False)


# --- C-rules ----------------------------------------------------------------

def test_c301_hedge_stack():
    assert "C301" in ids("These findings may possibly suggest a role for "
                         "household crowding.")
    assert "C301" not in ids("These findings suggest a role for household "
                             "crowding.")


def test_c302_overclaim_in_results():
    assert "C302" in ids("Results\n\nThis proves that stratification matters.")


def test_c303_causal_fires_on_world_claim():
    t = "Results\n\nVaccination reduced transmission across all quintiles."
    assert "C303" in ids(t)


def test_c303_quiet_on_author_action():
    t = "Results\n\nWe increased the sample size in the second wave."
    assert "C303" not in ids(t)


def test_c303_quiet_in_methods():
    t = "Methods\n\nVaccination reduced transmission in the simulation runs."
    assert "C303" not in ids(t)


@pytest.mark.parametrize("t", [
    # P31 (Q3): a change described, no cause in view
    "Results\n\nThe ward occupancy fell back to its usual level after "
    "the holiday.",
    "Results\n\nWeekly admissions increased sharply in the third month.",
])
def test_c303_quiet_on_intransitive_change(t):
    assert "C303" not in ids(t)


@pytest.mark.parametrize("t", [
    "Results\n\nBed nets lowered the incidence of malaria in every province.",
    "Results\n\nTransmission was reduced by the school closures.",
])
def test_c303_fires_on_transitive_or_passive_claims(t):
    assert "C303" in ids(t)


def test_c304_bare_significant():
    t = "Results\n\nThe difference between quintiles was significant."
    assert "C304" in ids(t)
    t2 = "Results\n\nThe difference was statistically significant (p=0.01)."
    assert "C304" not in ids(t2)


def test_c305_assertive():
    assert "C305" in ids("This clearly matters for control.")


# --- F601 acronyms ----------------------------------------------------------

def test_f601_fires_on_undefined():
    assert "F601" in ids("The WAIC favoured the stratified model.")


def test_f601_quiet_when_defined():
    t = ("We compared models using the widely applicable information "
         "criterion (WAIC). The WAIC favoured the stratified model.")
    assert "F601" not in ids(t)


def test_f601_allowlist():
    assert "F601" not in ids("The 95% CI excluded the null.")


# --- masking ----------------------------------------------------------------

def test_markdown_masking_skips_code_and_math():
    t = (
        "# Results\n\n"
        "Estimates were stable.\n\n"
        "```r\n# utilize prior to significant\nplot(1)\n```\n\n"
        "The rate $\\beta_{utilize}$ was fixed.\n"
    )
    found = ids(t, kind="markdown")
    assert "W201" not in found and "W202" not in found


def test_markdown_masking_skips_citations():
    t = "Prior work focused on age structure [@mossong2008; @prem2017].\n"
    doc = Document.from_text(t, "markdown")
    assert "@" not in doc.masked


def test_latex_masking_and_sections():
    t = (
        "\\section{Methods}\n"
        "Samples were incubated at 37 degrees \\cite{smith2020}.\n"
        "\\section{Results}\n"
        "The effect was significant.\n"
    )
    doc = Document.from_text(t, "latex")
    secs = [h.section for h in doc.headings]
    assert secs == ["methods", "results"]
    found = ids(t, kind="latex")
    assert "C304" in found          # bare 'significant' in Results
    assert "smith2020" not in doc.masked


def test_offsets_map_to_original():
    t = "## Discussion\n\nWe performed an estimation of the rate.\n"
    doc = Document.from_text(t, "markdown")
    out = [s for s in check(doc, NLP, show_preferences=True)
           if s.rule_id == "G102"]
    assert out
    s = out[0]
    assert doc.original[s.start:s.end] == "performed an estimation of"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_g107_quiet_on_et_al():
    assert "G107" not in ids("This was shown by Garcia et al. Rodriguez "
                             "Martinez Lopez previously.")


# --- dogfooding-tune regression tests (v0.1.1) ------------------------------

def test_g101_quiet_on_plain_long_subject_np():
    # long but uninterrupted subject NP — ordinary academic register
    # (12 words between subject and verb, but no comma/clause/apposition)
    t = ("The proportion of cases in the oldest age band of the rural "
         "cohort is shown below.")
    assert "G101" not in ids(t)


@pytest.mark.parametrize("t", [
    # P31 (Q3): list commas and bracketed citations/abbreviations are not
    # interruptions; a restrictive clause is part of a short-enough subject.
    "Wards with no admissions, transfers or discharges during the whole "
    "audit window were dropped.",
    "Every ward in the hospital building that reported fewer than "
    "three cases in the year was merged with a neighbour.",
    "Penalised splines with a smoothing parameter chosen by restricted "
    "maximum likelihood estimation (REML) worked well.",
    "The incidence rate in the northern and eastern districts of the city "
    "(12, 13) was "
    "lower than expected.",
])
def test_g101_quiet_on_lists_citations_and_short_restrictive_clauses(t):
    assert "G101" not in ids(t)


@pytest.mark.parametrize("t", [
    # a comma-bounded aside, a dash-bounded aside, a bracketed aside
    "The rainy season in the three lowland provinces, when standing water "
    "and breeding sites multiply, brings the yearly peak.",
    "The reporting delay — which varied between districts, between years "
    "and between the two laboratories — biased the early estimates.",
    "The attack rate (estimated from the serological survey of primary "
    "school children in the two northern districts) was higher than "
    "expected.",
    # a restrictive clause long enough to lose the reader
    "The proportion of household contacts who developed symptoms within "
    "two weeks of the index case being admitted to hospital was high.",
])
def test_g101_still_fires_on_real_interruptions(t):
    assert "G101" in ids(t)


def test_g104_quiet_on_method_by_phrase():
    # by-phrase names a criterion, not a doer
    t = "Results\n\nThe weekly incidence rates are stratified by region."
    assert "G104" not in ids(t)


def test_g104_quiet_on_pronoun_topic_subject():
    # proper-noun agent, but the pronoun subject marks topic continuity
    t = ("Results\n\nIt is distributed by the Ministry of Health in rural "
         "districts.")
    assert "G104" not in ids(t)


def test_g107_quiet_on_technical_proper_compound():
    t = ("Parameters were sampled with Markov chain Monte Carlo methods "
         "in Stan.")
    assert "G107" not in ids(t)


def test_c303_quiet_on_purpose_infinitive():
    t = ("Results\n\nChildren should wash their hands to prevent "
         "transmission in preschools.")
    assert "C303" not in ids(t)


def test_c303_quiet_on_modal_calibrated():
    t = "Discussion\n\nEarlier school closures might lead to fewer infections."
    assert "C303" not in ids(t)


def test_c303_quiet_inside_reporting_frame():
    t = ("Results\n\nWe estimated that closures averted twelve hundred "
         "cases over six years.")
    assert "C303" not in ids(t)


def test_c303_aggregates_repeats():
    t = ("Results\n\nVaccination reduced transmission. Vaccination reduced "
         "hospitalisations. Vaccination reduced mortality.")
    doc = Document.from_text(t, "plain")
    hits = [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == "C303"]
    assert len(hits) == 1 and "3 uses" in hits[0].message


def test_c301_quiet_on_reporting_verb_plus_complement_modal():
    # hedges within the window but split by the 'that' clause boundary
    t = "This suggests that earlier testing may shorten outbreaks."
    assert "C301" not in ids(t)


def test_f601_quiet_in_allcaps_title_zone():
    t = ("SPATIAL MODELS OF RAIN AND DENGUE RISK IN CITY PARKS FOR THE "
         "DEGREE OF DOCTOR OF PHILOSOPHY")
    assert "F601" not in ids(t)


def test_g103_quiet_on_compound_technical_nominals():
    t = ("The prediction models used notification data and the estimation "
         "procedure described previously.")
    assert "G103" not in ids(t)


def test_heading_not_merged_into_sentence():
    # heading text is masked, so it can never become a sentence subject
    t = "Results\n\nSelected variables are presented in the table below."
    doc = Document.from_text(t, "plain")
    assert "Results" not in doc.masked
    assert doc.section_at(len(t) - 5) == "results"


def test_f601_quiet_on_author_initials():
    t = "This was reported by Stokes EK, Zambrano LD, and Anderson KN."
    assert "F601" not in ids(t)


def test_f601_still_fires_after_definite_article():
    assert "F601" in ids("The DALY burden was computed for every scenario.")
