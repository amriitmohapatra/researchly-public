"""Article-type profiles (S4, owner request 2026-10-08) and the critical
reader's brief built from the same analysis. Synthetic text only.
"""

import re

import pytest

from researchly import api, profiles
from researchly.config import DOCUMENT_TYPES
from researchly.document import Document
from researchly.review import build_review, render_review
from tests.test_explanations import INTERNAL

NLP = api.get_nlp()

ARGUED = ("Vaccination mandates work. The evidence proves that mandates "
          "reduce transmission. It is known that uptake fell afterwards. "
          "We argue that mandates must return now.\n")

IMRAD = ("Introduction\n\nLittle is known about the burden.\n\n"
         "Methods\n\nWe fitted a model to weekly counts.\n\n"
         "Results\n\nCases fell by half.\n\nDiscussion\n\nThe fall was "
         "observed in every district.\n")


def ids(text, **kw):
    a = api.analyze(text, nlp=NLP, show_preferences=True, **kw)
    return a, sorted({s.rule_id for s in a.suggestions})


# --- the registry ---------------------------------------------------------------------

def test_config_types_are_the_profiles():
    assert DOCUMENT_TYPES == tuple(profiles.PROFILES)
    assert {"auto", "general", "manuscript", "commentary",
            "policy-brief"} <= set(DOCUMENT_TYPES)


def test_every_rule_switched_off_exists_and_has_a_plain_reason():
    from researchly.engine import REGISTRY, load_rules
    load_rules()
    for p in profiles.PROFILES.values():
        for rid, why in p.rules_off.items():
            assert rid in REGISTRY, (p.id, rid)
            assert len(why.split()) >= 4 and not INTERNAL.search(why)
        assert not INTERNAL.search(p.note + p.summary + p.label)


def test_listing_for_a_selector():
    rows = profiles.listing()
    assert [r["id"] for r in rows][:2] == ["auto", "general"]
    assert all(r["label"] and r["summary"] for r in rows)


# --- what a profile changes -----------------------------------------------------------

def test_general_is_the_engine_as_before():
    a, found = ids(ARGUED)
    assert a.profile.id == "general" and a.profile_guessed
    assert {"C302", "C303"} <= set(found)


def test_commentary_may_argue_assertively():
    a, found = ids(ARGUED, document_type="commentary")
    assert a.profile.id == "commentary" and not a.profile_guessed
    assert not {"C302", "C303", "AB802"} & set(found)
    assert "assertively" in a.profile.note


def word(*paras):
    return Document.from_word(
        [p if isinstance(p, dict) else {"text": p} for p in paras])


def test_commentary_body_is_argued_like_a_discussion():
    # a bare "significant" is judged in Results and Discussion; prose under
    # a topical heading is nowhere, unless the profile says it is argued
    doc = word({"text": "Why the ban matters", "style": "Heading 1"},
               "The effect of the ban was significant in every district.")
    assert "C304" not in ids(doc)[1]
    a, found = ids(doc, document_type="commentary")
    assert "C304" in found and a.document.section_at(30) == "discussion"


ABSTRACT = ("Dengue burden is rising across the region and vector control "
            "has been the mainstay of prevention for decades. We fitted a "
            "transmission model to weekly counts from three districts over "
            "two seasons and estimated the reproduction number in each of "
            "them. Cases fell by half after the campaign in every district, "
            "and the estimates were stable across seasons and across the "
            "model variants that we compared in full.\n")


def test_abstract_profile_judges_a_pasted_abstract():
    assert "AB802" not in ids(ABSTRACT)[1]
    a, found = ids(ABSTRACT, document_type="abstract")
    (h,) = [s for s in a.suggestions if s.rule_id == "AB802"]
    assert "Missing" in h.message and h.section == "abstract"


def test_response_to_reviewers_does_not_count_the_manuscripts_floats():
    text = "We thank the reviewer. The result is shown in Figure 3.\n"
    assert "X103" not in ids(text, document_type="response-to-reviewers")[1]


def test_unknown_type_is_general():
    assert profiles.resolve("poem")[0].id == "general"


# --- auto ---------------------------------------------------------------------------

def test_auto_guesses_a_research_article_from_imrad_headings():
    a, _ = ids(IMRAD)
    assert a.profile.id == "manuscript" and a.profile_guessed


def test_auto_guesses_a_policy_brief_from_its_headings():
    text = ("Key messages\n\nMandates work.\n\nContext\n\nUptake fell.\n\n"
            "Recommendations\n\nRestore the mandate.\n")
    assert ids(text)[0].profile.id == "policy-brief"
    doc = word({"text": "Context", "style": "Heading 1"}, "Uptake fell.",
               {"text": "Policy options", "style": "Heading 1"},
               "Restore the mandate.")
    assert ids(doc)[0].profile.id == "policy-brief"


def test_a_recommendation_in_running_text_is_not_a_policy_brief():
    text = "Our recommendations follow from the fit.\n\nKey messages were sent.\n"
    assert ids(text)[0].profile.id == "general"


@pytest.mark.parametrize("text", [
    "A short paragraph with no headings at all, pasted to check.\n",
    "Background\n\nSome prose under a single heading.\n",
])
def test_auto_never_guesses_abstract_or_commentary(text):
    assert ids(text)[0].profile.id == "general"


def test_chosen_type_wins_over_the_guess():
    assert ids(IMRAD, document_type="commentary")[0].profile.id == "commentary"


def test_remote_settings_carry_the_type():
    from researchly.config import Config, apply_remote
    cfg = apply_remote(Config(), {"document_type": "policy-brief"})
    assert cfg.document_type == "policy-brief"
    assert apply_remote(Config(), {"document_type": "x"}).document_type == "auto"


# --- the critical reader's brief --------------------------------------------------

def test_review_comes_from_the_same_analysis():
    a = api.analyze(IMRAD, nlp=NLP, with_review=True)
    r = a.review
    assert [q["id"] for q in r["questions"]] == ["A", "B", "C", "D", "E"]
    assert r["profile"] == "manuscript" and "Wallace" in r["source"]
    assert all(q["verdict"] for q in r["questions"])
    assert "review" in a.to_dict() and a.to_dict()["profile"]["id"] == "manuscript"


def test_review_is_off_unless_asked():
    assert api.analyze(IMRAD, nlp=NLP).review is None


def test_review_wording_has_no_internal_references():
    for text, kind in ((ARGUED, "general"), (IMRAD, "manuscript")):
        r = api.analyze(text, nlp=NLP, with_review=True,
                        document_type=kind).review
        for q in r["questions"]:
            assert not INTERNAL.search(q["question"] + q["verdict"])
            for p in q["points"]:
                assert not INTERNAL.search(p), p
        assert not INTERNAL.search(render_review(r))


def test_review_does_not_ask_a_commentary_for_limitations():
    doc = word({"text": "Why now", "style": "Heading 1"}, "Mandates work.",
               {"text": "What should change", "style": "Heading 1"},
               "Restore the mandate.")
    r = api.analyze(doc, nlp=NLP, with_review=True,
                    document_type="commentary").review
    d = next(q for q in r["questions"] if q["id"] == "D")
    assert not any("limitations section" in p for p in d["points"])
    text = ("Introduction\n\nMandates work.\n\nDiscussion\n\n"
            "Restore the mandate.\n")
    r = api.analyze(text, nlp=NLP, with_review=True,
                    document_type="manuscript").review
    d = next(q for q in r["questions"] if q["id"] == "D")
    assert any("No limitations section" in p for p in d["points"])
    assert any("expects" in p and "methods" in p for p in d["points"])


def test_review_quotes_the_aim_and_the_significance():
    text = ("Introduction\n\nWe therefore set out to determine whether "
            "the campaign changed transmission.\n\nDiscussion\n\nThese "
            "findings suggest that programmes should target adults.\n")
    r = api.analyze(text, nlp=NLP, with_review=True).review
    b = next(q for q in r["questions"] if q["id"] == "B")
    e = next(q for q in r["questions"] if q["id"] == "E")
    assert "stated" in b["verdict"] and b["evidence"]
    assert "stated" in e["verdict"] and e["evidence"]


def test_a_pasted_paragraph_is_not_asked_for_sections():
    r = api.analyze(ARGUED, nlp=NLP, with_review=True).review
    d = next(q for q in r["questions"] if q["id"] == "D")
    text = " ".join(d["points"])
    assert "limitations" not in text and "gap statement" not in text


def test_build_review_alone_still_works():
    r = build_review(Document.from_text(IMRAD), NLP)
    assert r["questions"] and "REVIEWER'S BRIEF" in render_review(r)
    assert re.search(r"\d+ words", render_review(r))


# --- Auto must not weaken a research article (Codex review R2) ---------------------

RESEARCH_WITH_RECS = (
    "Introduction\n\nLittle is known about the burden.\n\nMethods\n\nWe "
    "fitted a model to weekly counts.\n\nResults\n\nVaccination reduced "
    "transmission.\n\nDiscussion\n\nThe evidence proves that mandates reduce "
    "transmission.\n\nRecommendations\n\nRestore the mandate.\n")


def test_a_recommendations_heading_does_not_turn_an_article_into_a_brief():
    a, found = ids(RESEARCH_WITH_RECS)
    assert a.profile.id == "manuscript" and a.profile_guessed
    assert {"C302", "C303"} <= set(found)
    assert "Methods" in a.profile_evidence


@pytest.mark.parametrize("make", ["plain", "markdown", "word"])
def test_research_wins_in_every_format(make):
    if make == "word":
        doc = Document.from_word(
            [{"text": h, "style": "Heading 1"} if i % 2 == 0 else {"text": h}
             for i, h in enumerate(["Methods", "We fitted a model.",
                                    "Results", "Cases fell.",
                                    "Recommendations", "Restore it."])])
    else:
        text = RESEARCH_WITH_RECS if make == "plain" else (
            "# Methods\n\nWe fitted a model.\n\n# Results\n\nCases fell.\n\n"
            "# Recommendations\n\nRestore it.\n")
        doc = Document.from_text(text, make)
    assert profiles.guess(doc) == "manuscript"


def test_a_real_policy_brief_is_still_guessed_with_its_evidence():
    a, _ = ids("Key messages\n\nMandates work.\n\nRecommendations\n\n"
               "Restore the mandate.\n")
    assert a.profile.id == "policy-brief" and "Recommendations" in a.profile_evidence


def test_the_chosen_type_is_never_second_guessed():
    a, _ = ids(RESEARCH_WITH_RECS, document_type="policy-brief")
    assert a.profile.id == "policy-brief" and a.profile_evidence == ""


def test_policy_brief_does_not_expect_an_abstract():
    assert "abstract" not in profiles.PROFILES["policy-brief"].expected


# --- the brief says "not assessed" and abstains (Codex review R4) -----------------

def brief(text, **kw):
    r = api.analyze(text, nlp=NLP, with_review=True, **kw).review
    return {q["id"]: q for q in r["questions"]}, r


CAUSAL = ("Introduction\n\nLittle is known about the burden.\n\nResults\n\n"
          "Vaccination reduced transmission.\n\nDiscussion\n\nWe argue "
          "that mandates must return.\n")


def test_a_muted_check_is_not_assessed_not_absent():
    q, _ = brief(CAUSAL, disabled={"C303"})
    assert q["C"]["status"] == "not_assessed"
    assert "No unhedged" not in q["C"]["verdict"]
    q, _ = brief(CAUSAL)
    assert q["C"]["status"] == "detected" and q["C"]["evidence"]


def test_a_profile_that_switches_the_check_off_is_not_assessed():
    q, _ = brief(CAUSAL, document_type="commentary")
    assert q["C"]["status"] == "not_assessed"


def test_an_excerpt_without_an_introduction_makes_no_gap_claim():
    q, _ = brief("Discussion\n\nThe fit was stable across the districts.\n")
    assert not any("gap statement" in p for p in q["D"]["points"])
    assert not q["D"]["evidence"]


def test_no_claims_means_nothing_to_weigh():
    q, _ = brief("The specimens arrived on Tuesday.\n")
    assert q["D"]["status"] == "not_applicable"
    assert "Nothing" not in q["D"]["verdict"]


def test_absent_signals_are_worded_as_not_detected():
    q, r = brief("Methods\n\nWe fitted a model.\n")
    assert q["B"]["status"] == "not_detected" and "detected" in q["B"]["verdict"]
    assert "does not establish" in r["disclaimer"]


def test_every_detected_answer_has_evidence():
    q, _ = brief(CAUSAL + "\nThese findings suggest that programmes "
                 "should target adults.\n")
    for k in ("B", "C", "E"):
        if q[k]["status"] == "detected":
            assert q[k]["evidence"], k
