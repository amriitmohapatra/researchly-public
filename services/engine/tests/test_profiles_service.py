"""Article-type profiles and the critical reader's brief on the analysis
routes (S4). Synthetic text only."""

from __future__ import annotations

from researchly.config import DOCUMENT_TYPES
from researchly_service.schemas import (AnalyzeResponse, AnalyzeWordResponse,
                                        DocumentType, RulesResponse)

from test_privacy_canary import (CANARY, assert_logged_request,  # noqa: F401
                                 assert_no_canary_anywhere, capture)

ARGUED = ("Vaccination mandates work. The evidence proves that mandates "
          "reduce transmission. It is known that uptake fell afterwards. "
          "We argue that mandates must return now.\n")


def post(client, content=ARGUED, **options):
    return client.post("/v1/analyze",
                       json={"format": "plain", "content": content,
                             "options": options})


def test_the_contract_lists_every_engine_type():
    assert tuple(t.value for t in DocumentType) == DOCUMENT_TYPES


def test_default_profile_is_guessed_general(client):
    body = AnalyzeResponse.model_validate(post(client).json())
    assert body.profile.id is DocumentType.general and body.profile.guessed
    assert body.profile.note == "" and body.review is None
    assert {"C302", "C303"} <= {s.rule_id for s in body.suggestions}


def test_commentary_switches_the_hedging_prompts_off(client):
    body = AnalyzeResponse.model_validate(
        post(client, document_type="commentary").json())
    assert body.profile.id is DocumentType.commentary
    assert not body.profile.guessed and "assertively" in body.profile.note
    assert "C302" in body.profile.rules_off
    assert not {"C302", "C303"} & {s.rule_id for s in body.suggestions}


def test_unknown_type_is_refused(client):
    r = post(client, document_type="poem")
    assert r.status_code == 422


def test_review_on_request_with_five_questions(client):
    body = AnalyzeResponse.model_validate(post(client, review=True).json())
    assert body.review is not None
    assert [q.id for q in body.review.questions] == ["A", "B", "C", "D", "E"]
    assert body.review.words > 0 and "Wallace" in body.review.source
    assert all(q.verdict for q in body.review.questions)


def test_review_on_word_paragraphs(client):
    paras = [{"text": "Discussion", "style": "Heading 1"},
             {"text": ARGUED}]
    r = client.post("/v1/analyze-word",
                    json={"paragraphs": paras,
                          "options": {"review": True,
                                      "document_type": "commentary"}})
    body = AnalyzeWordResponse.model_validate(r.json())
    assert body.review is not None and body.profile.id is DocumentType.commentary


def test_review_evidence_is_the_callers_own_text_and_never_logged(
        client, capture):  # noqa: F811
    doc = (f"Introduction\n\nWe therefore set out to determine whether the "
           f"{CANARY} campaign changed transmission.\n\nDiscussion\n\n"
           "These findings suggest that programmes should target adults.\n")
    r = post(client, content=doc, review=True)
    assert r.status_code == 200
    quoted = [e for q in r.json()["review"]["questions"] for e in q["evidence"]]
    assert any(CANARY in e for e in quoted)        # the response may quote it
    assert_logged_request(capture, 200)
    assert_no_canary_anywhere(capture)             # nothing else may


def test_rules_route_lists_the_profiles(client):
    body = RulesResponse.model_validate(client.get("/v1/rules").json())
    ids = [p.id.value for p in body.profiles]
    assert ids[:2] == ["auto", "general"] and "commentary" in ids
    assert all(p.label and p.summary for p in body.profiles)


def test_learn_routes(client):
    from researchly_service.schemas import LearnCard, LearnResponse
    body = LearnResponse.model_validate(client.get("/v1/learn").json())
    ids = [c.id for c in body.cards]
    assert "causal-language" in ids and len(ids) == len(set(ids))
    one = LearnCard.model_validate(client.get("/v1/learn/causal-language").json())
    assert one.before != one.after and "C303" in one.rules
    r = client.get("/v1/learn/no-such-card")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_checklist_on_request_and_listed(client):
    text = ("Methods\n\nWe report forecasts of weekly cases four weeks ahead, "
            "with 95% prediction intervals.\n")
    body = AnalyzeResponse.model_validate(post(client, content=text,
                                               checklist="auto").json())
    assert body.checklist is not None and body.checklist.id == "epiforge"
    assert body.suggested_checklist == "epiforge"
    st = {i.id: i.status for i in body.checklist.items}
    assert st["horizon"] == "reported"
    rules = RulesResponse.model_validate(client.get("/v1/rules").json())
    assert [c.id for c in rules.checklists] == ["strobe", "consort", "prisma",
                                                "epiforge"]


def test_profile_evidence_is_returned(client):
    text = ("Methods\n\nWe fitted a model.\n\nResults\n\nCases fell.\n\n"
            "Recommendations\n\nRestore it.\n")
    body = AnalyzeResponse.model_validate(post(client, content=text).json())
    assert body.profile.id.value == "manuscript" and "Methods" in body.profile.evidence


def test_brief_statuses_and_disclaimer(client):
    body = AnalyzeResponse.model_validate(post(client, review=True,
                                               disabled_rules=["C303"]).json())
    q = {x.id: x for x in body.review.questions}
    assert q["A"].status == "yours" and q["C"].status == "not_assessed"
    assert "does not establish" in body.review.disclaimer
