"""Tests for the deterministic polish engine (transform.py) and G102 fix."""

import sys
from pathlib import Path

import spacy

from researchly.transform import polish, _expletive_edits
from researchly.document import Document
from researchly.engine import check

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "word-addin"))
import server as addin_server  # noqa: E402

NLP = spacy.load("en_core_web_sm")


def test_polish_composes_multiple_edits():
    t = ("We utilize household survey data in order to construct contact "
         "matrices, and we performed an estimation of the transmission "
         "rate for each and every scenario.")
    r = polish(t, NLP)
    assert r.changed
    assert "use household survey data to construct" in r.rewritten
    assert "estimated the transmission rate" in r.rewritten
    assert "every scenario" in r.rewritten
    assert "each and every" not in r.rewritten
    rules = {e["rule_id"] for e in r.edits}
    assert {"W201", "W202", "G102", "W206"} <= rules


def test_polish_conjugates_light_verbs_by_tense():
    r = polish("The team conducts a comparison of model fits.", NLP)
    assert "compares model fits" in r.rewritten


def test_polish_filler_deletion_recapitalizes():
    t = "It is important to note that estimates are preliminary."
    r = polish(t, NLP)
    assert r.rewritten == "Estimates are preliminary."


def test_polish_expletive_transform():
    t = "There are three factors that drive transmission in cities."
    r = polish(t, NLP)
    assert r.rewritten == "Three factors drive transmission in cities."
    assert any(e["rule_id"] == "G105" for e in r.edits)


def test_expletive_pattern_is_conservative():
    # no relativizer → no transform ("There is no evidence." must survive)
    # Takes (masked, original): the pattern is matched on the mask, but the
    # replacement is cut from the source and any span covering a masked
    # region is dropped — see test_w1_reliability.
    assert _expletive_edits("There is no evidence.",
                            "There is no evidence.") == []


def test_polish_doubled_word():
    r = polish("The results in the the table are final.", NLP)
    assert "in the table" in r.rewritten


def test_polish_protects_math_and_citations_markdown():
    t = ("We utilize the force of infection $\\lambda_i(t)$ in order to "
         "model transmission [@prem2017].")
    r = polish(t, NLP, kind="markdown")
    assert r.changed
    assert "$\\lambda_i(t)$" in r.rewritten          # math untouched
    assert "[@prem2017]" in r.rewritten              # citation untouched
    assert "use the force of infection" in r.rewritten
    assert "to model transmission" in r.rewritten


def test_polish_leaves_clean_text_alone():
    t = "We estimated the transmission rate for every scenario."
    r = polish(t, NLP)
    assert not r.changed
    assert r.rewritten == t


def test_polish_never_touches_unmatched_text_regions():
    # author's double-space style outside any edit must survive
    t = "We utilize diaries.  The second sentence keeps its spacing."
    r = polish(t, NLP)
    assert "diaries.  The" in r.rewritten


def test_polish_reports_judgement_flags_as_notes():
    t = ("Results\n\nVaccination reduced transmission. The difference "
         "was significant.")
    r = polish(t, NLP)
    joined = " ".join(r.notes)
    assert "C303" in joined and "C304" in joined


def test_polish_server_endpoint_shape():
    result = addin_server.transform.polish(
        "We utilize data in order to model spread.",
        addin_server.get_nlp()).to_dict()
    assert result["changed"]
    assert result["segments"] and result["edits"]
    ops = {s["op"] for s in result["segments"]}
    assert "del" in ops and "ins" in ops and "eq" in ops


def test_g102_of_absorption_multiword_object():
    doc = Document.from_text(
        "We conducted a comparison of the fitted models.", "plain")
    hits = [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == "G102"]
    assert hits
    s = hits[0]
    t = doc.original
    assert t[:s.start] + s.replacement + t[s.end:] == \
        "We compared the fitted models."


def test_polish_cascades_to_fixpoint():
    # deleting the filler must expose the expletive opener to a second pass
    t = ("It is important to note that there are three factors that drive "
         "transmission.")
    r = polish(t, NLP)
    assert r.rewritten == "Three factors drive transmission."
    rules = [e["rule_id"] for e in r.edits]
    assert "W205" in rules and "G105" in rules
