"""The narrative map on the analysis routes (S4). Synthetic text only."""

from __future__ import annotations

from researchly_service.schemas import AnalyzeResponse, AnalyzeWordResponse

from test_privacy_canary import (CANARY, assert_logged_request,  # noqa: F401
                                 assert_no_canary_anywhere, capture)

PAPER = ("Introduction\n\nDengue remains a leading cause of admission. "
         "However, little is known about how it varies between districts. "
         "We therefore set out to estimate transmission.\n\n"
         "Discussion\n\nIn this study we found that transmission varied. "
         "This suggests that control should be targeted, because the "
         "districts differ. This study has limitations: reporting was "
         "incomplete.\n")


def post(client, content=PAPER, **options):
    return client.post("/v1/analyze",
                       json={"format": "plain", "content": content,
                             "options": options})


def test_off_by_default(client):
    body = AnalyzeResponse.model_validate(post(client).json())
    assert body.narrative is None


def test_map_on_request(client):
    body = AnalyzeResponse.model_validate(post(client, narrative=True).json())
    n = body.narrative
    assert n is not None
    assert [s.section for s in n.sections] == ["introduction", "discussion"]
    intro = n.sections[0]
    assert [m.id for m in intro.moves] == ["territory", "gap", "aim"]
    assert all(m.status.value == "present" for m in intro.moves)
    disc = n.sections[1]
    missing = [m for m in disc.moves if m.status.value == "missing"]
    assert missing and all(m.question.endswith("?") and m.frame for m in missing)
    assert n.hedging and n.source and "Swales" in n.source


def test_map_on_word_paragraphs(client):
    paras = [{"text": "Introduction", "style": "Heading 1"},
             {"text": "However, little is known about dengue here."}]
    r = client.post("/v1/analyze-word",
                    json={"paragraphs": paras, "options": {"narrative": True}})
    body = AnalyzeWordResponse.model_validate(r.json())
    assert body.narrative is not None
    assert body.narrative.sections[0].section == "introduction"


def test_evidence_reaches_only_the_response(client, capture):  # noqa: F811
    doc = PAPER.replace("estimate transmission",
                        f"estimate {CANARY} transmission")
    r = post(client, content=doc, narrative=True)
    assert r.status_code == 200
    quoted = [m["evidence"] or "" for s in r.json()["narrative"]["sections"]
              for m in s["moves"]]
    assert any(CANARY in e for e in quoted)
    assert_logged_request(capture, 200)
    assert_no_canary_anywhere(capture)
