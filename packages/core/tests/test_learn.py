"""Learn cards (S4): every rule and every narrative move leads to a lesson,
in everyday words, with invented examples. Synthetic text only."""

import pytest

from researchly import api, learn
from researchly.discourse import moves as moves_mod
from researchly.engine import REGISTRY, load_rules
from tests.test_explanations import INTERNAL

NLP = api.get_nlp()


def test_every_rule_has_a_card():
    load_rules()
    missing = [r for r in REGISTRY if r not in learn.RULE_CARD]
    assert missing == []
    assert set(learn.RULE_CARD) <= set(REGISTRY)      # no card for a dead rule


def test_every_card_is_reached():
    reached = set(learn.RULE_CARD.values())
    for section, schema in moves_mod.SCHEMAS.items():
        for mid in schema:
            reached.add(learn.card_for_move(section, mid))
    reached |= set(learn.LINK_CARD.values())
    assert set(learn.CARDS) == reached


def test_every_move_and_link_resolves():
    for section, schema in moves_mod.SCHEMAS.items():
        for mid in schema:
            assert learn.card_for_move(section, mid) in learn.CARDS
    for card in learn.LINK_CARD.values():
        assert card in learn.CARDS


@pytest.mark.parametrize("card", list(learn.CARDS.values()), ids=lambda c: c.id)
def test_a_card_teaches_in_plain_words(card):
    for field in (card.title, card.summary, card.lesson, card.before,
                  card.after, card.habit):
        assert field.strip() and not INTERNAL.search(field), (card.id, field)
    assert card.before != card.after
    assert 25 <= len(card.lesson.split()) <= 110
    assert card.group in learn.GROUPS
    assert len(card.citation) > 15


def test_listing_is_grouped_in_reading_order():
    groups = [c["group"] for c in learn.listing()]
    order = [learn.GROUPS.index(g) for g in groups]
    assert order == sorted(order) and len(groups) == len(learn.CARDS)


def test_suggestions_carry_their_card():
    a = api.analyze("Methods\n\nWe fitted the the model.\n", nlp=NLP)
    (s,) = [s for s in a.suggestions if s.rule_id == "W207"]
    assert s.learn_ref == "spelling-and-grammar"
    assert s.to_dict()["learn_ref"] == "spelling-and-grammar"


def test_narrative_moves_and_links_carry_their_card():
    text = ("Introduction\n\nDengue remains a leading cause of admission. "
            "We argue that control must change now.\n\nDiscussion\n\n"
            "We argue that density drives transmission.\n")
    n = api.analyze(text, nlp=NLP, with_narrative=True).narrative
    intro = next(s for s in n["sections"] if s["section"] == "introduction")
    assert {m["learn_ref"] for m in intro["moves"]} == {"introduction"}
    disc = next(s for s in n["sections"] if s["section"] == "discussion")
    refs = {m["id"]: m["learn_ref"] for m in disc["moves"]}
    assert refs["interpretation"] == "warranting" and refs["summary"] == "discussion"
    assert all(link["learn_ref"] in learn.CARDS for link in n["missing_links"])


def test_the_web_copy_of_the_cards_is_current():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "contract" / "learn.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "cards": learn.listing()}, (
        "packages/contract/learn.json is stale: run "
        "`python -m researchly.learn packages/contract/learn.json` from "
        "packages/core's parent")
