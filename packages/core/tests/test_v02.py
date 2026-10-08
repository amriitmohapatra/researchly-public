"""Tests for v0.2: telemetry, engine aggregation, abbreviation-list awareness."""

import importlib
import json
import sys
from pathlib import Path

import pytest
import spacy

from researchly.document import Document
from researchly.engine import check
from researchly import telemetry

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "word-addin"))
import server as addin_server  # noqa: E402

NLP = spacy.load("en_core_web_sm")


def ids(text, kind="plain"):
    doc = Document.from_text(text, kind)
    return [s.rule_id for s in check(doc, NLP, show_preferences=True)]


# --- telemetry --------------------------------------------------------------

@pytest.fixture()
def tmp_telemetry(tmp_path, monkeypatch):
    d = tmp_path / ".researchly"
    monkeypatch.setattr(telemetry, "DIR", d)
    monkeypatch.setattr(telemetry, "FILE", d / "telemetry.jsonl")
    return d


def test_telemetry_roundtrip(tmp_telemetry):
    assert telemetry.log_event("shown", "G101", section="methods", count=3)
    assert telemetry.log_event("dismissed", "G101", section="methods")
    assert telemetry.log_event("applied", "W201")
    assert not telemetry.log_event("bogus-event", "G101")
    events = telemetry.read_events()
    assert len(events) == 3
    report = telemetry.summarize(events)
    assert report["G101"]["shown"] == 3
    assert report["G101"]["dismissed"] == 1
    assert report["G101"]["keep_rate"] == round(2 / 3, 2)
    assert report["W201"]["applied"] == 1


def test_telemetry_never_raises_on_bad_file(tmp_telemetry):
    tmp_telemetry.mkdir(parents=True)
    (tmp_telemetry / "telemetry.jsonl").write_text("not json\n{\"t\":1}\n")
    assert isinstance(telemetry.read_events(), list)


def test_server_telemetry_endpoint(tmp_telemetry):
    # exercise the same code path the HTTP handler uses
    for ev in [{"event": "shown", "rule": "C303", "section": "results",
                "n": 2},
               {"event": "muted", "rule": "W203"}]:
        telemetry.log_event(str(ev.get("event")), str(ev.get("rule")),
                            section=str(ev.get("section", "unknown")),
                            source="word", count=int(ev.get("n", 1)))
    rep = telemetry.summarize()
    assert rep["C303"]["shown"] == 2
    assert rep["W203"]["muted"] == 1


# --- engine aggregation -----------------------------------------------------

def test_c304_aggregates_per_section():
    t = ("Results\n\n"
         "The first difference was significant. The second difference was "
         "significant. The third difference was also significant.\n\n"
         "Discussion\n\n"
         "The effect was significant.")
    doc = Document.from_text(t, "plain")
    hits = [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == "C304"]
    # one per section, not one per occurrence
    assert len(hits) == 2
    results_hit = next(s for s in hits if s.section == "results")
    assert "3 similar in this section" in results_hit.message
    discussion_hit = next(s for s in hits if s.section == "discussion")
    assert "similar" not in discussion_hit.message


# --- F601 abbreviation-list awareness ---------------------------------------

def test_f601_respects_abbreviation_list():
    t = ("List of Abbreviations\n\n"
         "WAIC — Widely Applicable Information Criterion\n"
         "DALY: Disability-Adjusted Life Year\n\n"
         "Results\n\n"
         "The WAIC favoured the stratified model and the DALY burden fell.")
    assert "F601" not in ids(t)


def test_f601_still_fires_without_list():
    t = "Results\n\nThe WAIC favoured the stratified model."
    assert "F601" in ids(t)


# --- v0.7: metadiscourse meter + W210 + review lens -------------------------

def test_metrics_metadiscourse_meter():
    from researchly import metrics as metrics_mod
    t = ("We clearly established that the effect must always hold. "
         "Perhaps it may possibly vary somewhat across settings.")
    doc = Document.from_text(t, "plain")
    m = metrics_mod.compute(NLP(doc.masked), doc)
    d = m.to_dict()
    assert d["boosters_per_100w"] > 0
    assert d["hedges_per_100w"] > 0
    assert d["self_mention_per_100w"] > 0
    assert "1" in d["hedge_booster_balance"] or "balanced" in \
        d["hedge_booster_balance"] or "heavy" in d["hedge_booster_balance"]


def test_w210_flags_mixed_variants():
    t = ("We are modelling transmission in cities. The modeling framework "
         "uses contact matrices. Modelling choices matter.")
    doc = Document.from_text(t, "plain")
    hits = [s for s in check(doc, NLP, disabled={"LT001"},
                             show_preferences=True)
            if s.rule_id == "W210"]
    assert len(hits) == 1
    assert "modelling" in hits[0].message and "modeling" in hits[0].message
    assert hits[0].replacement == "modelling"      # majority form wins


def test_w210_quiet_on_consistent_usage():
    t = "We are modelling transmission. The modelling framework is simple."
    doc = Document.from_text(t, "plain")
    assert not [s for s in check(doc, NLP, disabled={"LT001"},
                                 show_preferences=True)
                if s.rule_id == "W210"]


def test_review_lens_report():
    from researchly.review import build_review, render_review
    t = ("Introduction\n\n" + ("Dengue burden is rising across Southeast "
         "Asia and vector control has been the mainstay of prevention for "
         "decades in most affected countries of the region. ") * 5 +
         "However, income-related heterogeneity remains unquantified. "
         "We aimed to quantify its contribution.\n\n"
         "Limitations\n\nOur data may undercount mild cases.\n\n"
         "Conclusion\n\nThese findings suggest equity-aware strategies "
         "could inform policy.")
    r = build_review(t, NLP)
    assert r["gap_present"] and r["aim"]["present"]
    assert r["has_limitations"]
    assert r["significance"]["present"]
    report = render_review(r)
    assert "REVIEWER'S BRIEF" in report
    assert "An aim is stated." in report
    assert "A limitations section is present" in report
