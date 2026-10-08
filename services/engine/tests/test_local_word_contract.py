"""The local Word server answers the same contract as the hosted engine
(Codex review R1). Every option the contract's AnalyzeOptions defines is
posted to the real local handler, and its unmodified JSON is validated
against the hosted response model, which forbids unknown fields. A new
contract option that the local server does not accept fails here.
Synthetic text only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from researchly_service.schemas import AnalyzeOptions, AnalyzeWordResponse

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def server():
    path = ROOT / "apps" / "word-addin" / "server.py"
    spec = importlib.util.spec_from_file_location("local_word_server", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_word_server"] = mod
    spec.loader.exec_module(mod)
    return mod


PARAS = [{"text": "Introduction", "style": "Heading 1"},
         {"text": "Little is known about the burden. We aimed to estimate it."},
         {"text": "Methods", "style": "Heading 1"},
         {"text": "We fitted a renewal model to weekly counts."},
         {"text": "Results", "style": "Heading 1"},
         {"text": "Vaccination reduced transmission in the the north."},
         {"text": "Discussion", "style": "Heading 1"},
         {"text": "The evidence proves that mandates work."}]

EVERY_OPTION = {
    "show_preferences": True, "disabled_rules": ["W204"], "mode": "revise",
    "document_type": "auto", "review": True, "narrative": True,
    "checklist": "auto",
}


def test_every_contract_option_is_covered_here():
    assert set(EVERY_OPTION) == set(AnalyzeOptions.model_fields)


def test_the_local_server_accepts_every_option_and_answers_the_contract(server):
    body = server.analyze_word({"paragraphs": PARAS, "options": EVERY_OPTION})
    raw = json.loads(json.dumps(body))           # exactly what the browser gets
    resp = AnalyzeWordResponse.model_validate(raw)    # extra=forbid
    assert resp.review is not None and resp.narrative is not None
    assert resp.profile.id.value == "manuscript"
    assert all(s.plain for s in resp.suggestions)
    assert any(s.learn_ref for s in resp.suggestions)


@pytest.mark.parametrize("mode,doc_type", [("draft", "auto"),
                                           ("revise", "commentary")])
def test_draft_revise_and_an_explicit_profile(server, mode, doc_type):
    body = server.analyze_word({"paragraphs": PARAS, "options": {
        "mode": mode, "document_type": doc_type, "review": mode == "revise"}})
    resp = AnalyzeWordResponse.model_validate(json.loads(json.dumps(body)))
    assert resp.mode.value == mode
    assert (resp.review is not None) == (mode == "revise")
    if doc_type == "commentary":
        assert resp.profile.id.value == "commentary" and not resp.profile.guessed


def test_the_older_option_set_still_works(server):
    body = server.analyze_word({"paragraphs": PARAS, "options": {
        "show_preferences": False, "disabled_rules": [], "mode": "revise"}})
    AnalyzeWordResponse.model_validate(json.loads(json.dumps(body)))


@pytest.mark.parametrize("bad", [{"document_type": "poem"}, {"review": "yes"},
                                 {"checklist": "astrology"}, {"colour": "red"}])
def test_bad_options_are_refused(server, bad):
    with pytest.raises(server.ContractError):
        server.parse_word_request({"paragraphs": PARAS, "options": bad})
