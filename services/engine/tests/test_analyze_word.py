"""POST /v1/analyze-word: the hosted Word add-in (S3), and Draft / Revise
mode (P1) on every analysis route. Synthetic text only."""

from __future__ import annotations

import pytest

from researchly_service.schemas import (AnalyzeResponse, AnalyzeWordResponse,
                                        MAX_CONTENT_CHARS)

from test_privacy_canary import (CANARY, assert_logged_request,  # noqa: F401
                                 assert_no_canary_anywhere, capture)

PARAS = [{"text": "Results", "style": "Heading 1"},
         {"text": "Cases rose in the the north and the the south."},
         {"text": "Figure 1. Weekly cases by district and season.",
          "style": "Caption"},
         {"text": "0.42", "kind": "table"}]


def post(client, paragraphs=PARAS, **options):
    return client.post("/v1/analyze-word",
                       json={"paragraphs": paragraphs, "options": options})


def test_response_follows_the_contract(client):
    r = post(client)
    assert r.status_code == 200, r.text
    body = AnalyzeWordResponse.model_validate(r.json())     # extra=forbid
    assert body.mode.value == "revise" and body.hidden_by_mode == 0
    assert body.coverage.paragraphs == 4
    assert body.coverage.table_paragraphs == 1
    assert "footnotes" in body.coverage.not_checked


def test_every_location_finds_its_text(client):
    body = post(client).json()
    doubled = [s for s in body["suggestions"] if s["rule_id"] == "W207"]
    assert len(doubled) == 2
    for s in body["suggestions"]:
        loc = s["location"]
        text = PARAS[loc["paragraph"]]["text"]
        assert text[loc["start"]:loc["end"]] == s["text"]
        if loc["exact"]:
            found = -1
            for _ in range(loc["occurrence"] + 1):
                found = text.index(loc["snippet"], found + 1)
            assert found == loc["start"]
    assert sorted(d["location"]["occurrence"] for d in doubled) == [0, 1]


def test_draft_mode_holds_back_document_checks(client):
    revise = post(client).json()
    draft = post(client, mode="draft").json()
    assert "X101" in {s["rule_id"] for s in revise["suggestions"]}
    assert "X101" not in {s["rule_id"] for s in draft["suggestions"]}
    assert draft["mode"] == "draft" and draft["hidden_by_mode"] >= 1
    assert "W207" in {s["rule_id"] for s in draft["suggestions"]}


def test_mode_on_the_paste_route_too(client):
    r = client.post("/v1/analyze", json={
        "content": "Methods\n\nWe fitted a latent class model (LCM).\n",
        "options": {"mode": "draft", "show_preferences": True}})
    body = AnalyzeResponse.model_validate(r.json())
    assert body.mode.value == "draft"
    assert "F613" not in {s.rule_id for s in body.suggestions}


def test_rules_report_their_scope(client):
    rules = {r["id"]: r for r in client.get("/v1/rules").json()["rules"]}
    assert rules["X101"]["scope"] == "document"
    assert rules["W207"]["scope"] == "sentence"


@pytest.mark.parametrize("payload,status", [
    ({"paragraphs": []}, 422),
    ({"paragraphs": [{"text": "x", "kind": "footnote"}]}, 422),
    ({"paragraphs": [{"text": "x", "colour": "red"}]}, 422),
    ({"paragraphs": [{"text": "x"}], "options": {"mode": "chapter"}}, 422),
    ({"content": "x"}, 422),
])
def test_bad_requests_are_refused(client, payload, status):
    assert client.post("/v1/analyze-word", json=payload).status_code == status


def test_over_the_character_cap(client):
    para = {"text": "a " * 100_000}
    n = MAX_CONTENT_CHARS // len(para["text"]) + 1
    r = client.post("/v1/analyze-word", json={"paragraphs": [para] * n})
    assert r.status_code in (413, 422)


def test_word_text_never_reaches_a_log(client, capture):  # noqa: F811
    paras = [{"text": "Discussion", "style": "Heading 1"},
             {"text": f"The {CANARY} model was very clear {CANARY}."},
             {"text": CANARY, "kind": "table"}]
    r = post(client, paras)
    assert r.status_code == 200, r.text
    rec = assert_logged_request(capture, 200)
    assert rec.format == "word"
    bad = client.post("/v1/analyze-word",
                      json={"paragraphs": [{"text": CANARY, "kind": CANARY}]})
    assert bad.status_code == 422
    assert_no_canary_anywhere(capture, bad)
