"""Draft / Revise mode (P1, S3): one setting in config.py, shared by every
surface. Draft shows sentence-level checks only and counts what it held
back. Synthetic text only."""

import pytest

from researchly import api, config as config_mod
from researchly.config import Config, apply_remote
from researchly.document import Document
from researchly.engine import REGISTRY, load_rules

NLP = api.get_nlp()

# A Figure never cited (X101, document-level) and a doubled word (W207,
# sentence-level), in a Word document so the structural rules run.
PARAS = [{"text": "Results", "style": "Heading 1"},
         {"text": "Cases rose in the the north."},
         {"text": "Figure 1. Weekly cases by district and season.",
          "style": "Caption"}]


def run(mode: str):
    cfg = Config(mode=mode)
    return api.analyze(Document.from_word(PARAS), nlp=NLP, cfg=cfg)


def test_revise_shows_everything():
    a = run("revise")
    ids = {s.rule_id for s in a.suggestions}
    assert {"W207", "X101"} <= ids and a.hidden_by_mode == 0


def test_draft_holds_back_document_checks_and_counts_them():
    a = run("draft")
    ids = {s.rule_id for s in a.suggestions}
    assert "W207" in ids and "X101" not in ids
    assert a.hidden_by_mode >= 1
    assert a.to_dict()["hidden_by_mode"] == a.hidden_by_mode


def test_every_rule_has_a_known_scope():
    load_rules()
    assert {r.scope for r in REGISTRY.values()} <= {"sentence", "document"}
    doc_rules = {r.id for r in REGISTRY.values() if r.scope == "document"}
    assert {"X101", "X103", "F612", "F613", "W211", "AB802"} <= doc_rules
    # spelling, grammar and the sentence craft rules stay in Draft
    assert {"S001", "LT001", "W207", "G106"}.isdisjoint(doc_rules)


def test_unknown_scope_is_refused():
    from researchly.engine import Category, rule
    with pytest.raises(ValueError):
        rule("Z999", "x", Category.IMPROVEMENT, "x", "x", scope="chapter")


@pytest.mark.parametrize("data,expected", [
    ({"mode": "draft"}, "draft"),
    ({"mode": "revise"}, "revise"),
    ({"mode": "chapter"}, "revise"),      # unknown: ignored
    ({}, "revise"),
])
def test_mode_from_the_account(data, expected):
    assert apply_remote(Config(), data).mode == expected


def test_mode_round_trips_through_toml(tmp_path):
    cfg = Config(mode="draft")
    path = tmp_path / ".researchly.toml"
    path.write_text(config_mod.dumps(cfg))
    assert config_mod.load(tmp_path / "chapter.tex").mode == "draft"
