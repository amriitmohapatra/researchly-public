"""Responses match contract v1 and keep the engine's promises through HTTP.

- shapes validate against the contract's own pydantic models (extra=forbid);
- Q10: every suggestion, and every rule in the registry, has a non-empty
  `why` and `source`;
- section awareness, preference hiding and per-request muting survive the
  trip through the API (CLAUDE.md #3, #4).
"""

from __future__ import annotations

import hashlib
import re

import researchly
from researchly.engine import REGISTRY

from researchly_service.schemas import (AnalyzeResponse, HealthResponse,
                                        RulesResponse)

from conftest import (DISCUSSION_PASSIVE, METHODS_PASSIVE, PREFERENCE_TEXT,
                      analyze, rule_ids)

SAMPLE = (
    "Introduction\n\n"
    "Dengue transmision has risen sharply in the region. It is very clear "
    "that urbanisation leads to more cases.\n\n"
    "Methods\n\n"
    "Weekly case counts were fitted with a renewal-equation model by the "
    "study team. The data was analysed in R.\n\n"
    "Discussion\n\n"
    "These results are proven by the model and was robust to priors.\n"
)

from researchly import learn as _learn  # noqa: E402
LEARN_IDS = set(_learn.CARDS)


def test_analyze_validates_against_the_contract(client):
    r = analyze(client, SAMPLE)
    assert r.status_code == 200
    body = r.json()
    parsed = AnalyzeResponse.model_validate(body)       # extra=forbid
    assert parsed.schema_version == "1"
    assert parsed.suggestions, "sample text should draw suggestions"
    assert parsed.engine.core_version == researchly.__version__
    assert parsed.engine.rules_loaded == len(REGISTRY) > 0
    assert parsed.elapsed_ms >= 0
    assert parsed.metrics is not None and parsed.metrics.words > 0
    assert {"introduction", "methods", "discussion"} <= set(
        parsed.sections_detected)
    assert {t.tier for t in parsed.health} >= {"parser", "spelling",
                                              "grammar", "gec"}
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])


def test_every_suggestion_is_explained_q10(client):
    for text in (SAMPLE, PREFERENCE_TEXT, DISCUSSION_PASSIVE):
        body = analyze(client, text, show_preferences=True).json()
        for s in body["suggestions"]:
            assert s["why"].strip(), s["rule_id"]
            assert s["source"].strip(), s["rule_id"]
            assert s["message"].strip(), s["rule_id"]


def test_every_rule_in_the_registry_is_explained_q10(client):
    body = client.get("/v1/rules").json()
    RulesResponse.model_validate(body)
    assert len(body["rules"]) == len(REGISTRY)
    for r in body["rules"]:
        assert r["why"].strip() and r["source"].strip(), r["id"]
    ids = [r["id"] for r in body["rules"]]
    assert ids == sorted(ids)
    g104 = next(r for r in body["rules"] if r["id"] == "G104")
    assert "methods" in g104["sections_excluded"]


def test_suggestion_ids_spans_and_text_are_consistent(client):
    body = analyze(client, SAMPLE).json()
    again = analyze(client, SAMPLE).json()
    assert [s["id"] for s in body["suggestions"]] == \
        [s["id"] for s in again["suggestions"]]          # stable
    lines = SAMPLE.split("\n")
    for s in body["suggestions"]:
        sp = s["span"]
        assert SAMPLE[sp["start"]:sp["end"]] == s["text"]
        raw = "\x1f".join((s["rule_id"], str(sp["start"]), str(sp["end"]),
                           s["text"]))
        assert s["id"] == hashlib.sha1(raw.encode()).hexdigest()
        assert sp["line"] >= 1 and sp["col"] >= 1
        assert lines[sp["line"] - 1][sp["col"] - 1:].startswith(
            s["text"].split("\n")[0])
        # Every suggestion leads to a Learn card (S4).
        assert s["learn_ref"] in LEARN_IDS
        assert 0.0 <= s["confidence"] <= 1.0


def test_counts_match_shown_suggestions(client):
    body = analyze(client, SAMPLE).json()
    tally = {}
    for s in body["suggestions"]:
        tally[s["category"]] = tally.get(s["category"], 0) + 1
    assert tally == body["counts"]


def test_passive_voice_is_never_flagged_in_methods(client):
    assert "G104" not in rule_ids(analyze(client, METHODS_PASSIVE))
    assert "G104" in rule_ids(analyze(client, DISCUSSION_PASSIVE))


def test_preferences_hidden_by_default_with_a_count(client):
    hidden = analyze(client, PREFERENCE_TEXT).json()
    assert not any(s["category"] == "preference"
                   for s in hidden["suggestions"])
    assert hidden["hidden_preferences"] >= 1
    shown = analyze(client, PREFERENCE_TEXT, show_preferences=True).json()
    prefs = [s for s in shown["suggestions"] if s["category"] == "preference"]
    assert len(prefs) == hidden["hidden_preferences"]
    assert shown["hidden_preferences"] == 0
    assert "W204" in {s["rule_id"] for s in prefs}


def test_disabled_rules_are_honoured(client):
    assert "G104" in rule_ids(analyze(client, DISCUSSION_PASSIVE))
    muted = analyze(client, DISCUSSION_PASSIVE, disabled_rules=["G104"])
    assert muted.status_code == 200
    assert "G104" not in rule_ids(muted)


def test_formats_are_accepted(client):
    md = "## Methods\n\nThe model was calibrated by the authors.\n"
    tex = ("\\section{Discussion}\nThe model was calibrated by the "
           "authors \\cite{ref1}.\n")
    r_md = analyze(client, md, fmt="markdown")
    r_tex = analyze(client, tex, fmt="latex")
    assert r_md.status_code == r_tex.status_code == 200
    assert "methods" in r_md.json()["sections_detected"]
    assert "discussion" in r_tex.json()["sections_detected"]
    assert "G104" in rule_ids(r_tex) and "G104" not in rule_ids(r_md)


def test_health_and_rules_shapes(client):
    h = client.get("/v1/health")
    assert h.status_code == 200
    body = HealthResponse.model_validate(h.json())
    assert body.engine.rules_loaded == len(REGISTRY)
    assert "x-request-id" in h.headers
