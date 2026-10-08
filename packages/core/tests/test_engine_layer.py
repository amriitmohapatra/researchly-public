"""Tests for the W0 engine changes: suggestion enrichment, overlap
resolution between correction tiers, and the safe-fix declaration."""

import pytest
import spacy

from researchly import engine as engine_mod
from researchly import transform
from researchly.document import Document
from researchly.engine import (REGISTRY, Category, Suggestion, check,
                               _resolve_overlaps)

NLP = spacy.load("en_core_web_sm")


def _sugg(start, end, tier, rule_id="X", conf=1.0,
          category=Category.CORRECTION):
    return Suggestion(message="m", start=start, end=end, tier=tier,
                      rule_id=rule_id, confidence=conf, category=category)


# --- enrichment -------------------------------------------------------------

def test_suggestions_carry_why_and_source():
    """Every surface used to re-join these out of REGISTRY by hand."""
    doc = Document.from_text("We utilize a model in order to predict.",
                             "plain")
    suggestions = check(doc, NLP, show_preferences=True)
    assert suggestions
    for s in suggestions:
        assert s.why, f"{s.rule_id} carries no explanation"
        assert s.why == REGISTRY[s.rule_id].why
        assert s.source == REGISTRY[s.rule_id].source
        assert s.tier and s.fix_safety


def test_to_dict_exposes_the_new_fields():
    doc = Document.from_text("We utilize a model.", "plain")
    d = check(doc, NLP)[0].to_dict()
    for field in ("why", "source", "tier", "fix_safety", "confidence"):
        assert field in d, f"{field} missing from the surface payload"


# --- overlap resolution -----------------------------------------------------

def test_overlapping_correction_tiers_are_deduped():
    """Spelling, grammar and GEC all edit the same words; without this the
    writer sees one typo up to three times."""
    kept = _resolve_overlaps([
        _sugg(10, 15, "spelling", "S001"),
        _sugg(10, 15, "grammar", "LT001"),
    ])
    assert len(kept) == 1
    assert kept[0].tier == "spelling"       # explainable tier wins


def test_gec_loses_to_the_explainable_tiers():
    kept = _resolve_overlaps([
        _sugg(4, 9, "gec", "GEC001"),
        _sugg(4, 9, "grammar", "LT001"),
    ])
    assert [s.tier for s in kept] == ["grammar"]


def test_longer_span_wins_over_shorter():
    kept = _resolve_overlaps([
        _sugg(10, 12, "spelling", "S001"),
        _sugg(8, 20, "grammar", "LT001"),
    ])
    assert [s.tier for s in kept] == ["grammar"]


def test_non_overlapping_corrections_all_survive():
    kept = _resolve_overlaps([
        _sugg(0, 5, "spelling"),
        _sugg(10, 15, "grammar"),
        _sugg(20, 25, "gec"),
    ])
    assert len(kept) == 3


def test_adjacent_spans_do_not_count_as_overlapping():
    kept = _resolve_overlaps([
        _sugg(0, 5, "spelling"),
        _sugg(5, 10, "grammar"),
    ])
    assert len(kept) == 2


def test_craft_suggestions_are_never_deduped_against_corrections():
    """A note about a 60-word sentence and a typo inside it are different
    observations that happen to share coordinates. Losing either loses signal.
    """
    kept = _resolve_overlaps([
        _sugg(0, 200, "craft", "G106", category=Category.IMPROVEMENT),
        _sugg(50, 55, "spelling", "S001"),
        _sugg(50, 55, "lens", "AB802", category=Category.CONVENTION),
    ])
    assert len(kept) == 3


def test_overlap_resolution_preserves_input_order():
    """check() sorts afterwards, but resolution must not shuffle."""
    given = [_sugg(0, 5, "craft", "A", category=Category.IMPROVEMENT),
             _sugg(10, 15, "spelling", "S001"),
             _sugg(20, 25, "craft", "B", category=Category.IMPROVEMENT)]
    assert [s.rule_id for s in _resolve_overlaps(given)] == ["A", "S001", "B"]


def test_single_correction_is_a_no_op():
    given = [_sugg(0, 5, "spelling")]
    assert _resolve_overlaps(given) == given


# --- safe-fix declaration ---------------------------------------------------

def test_safe_fix_set_matches_the_polish_rules():
    """`fix_safety="safe"` is what a bulk-apply button is allowed to touch,
    and Polish is what composes those same edits. If the two ever disagree,
    one of them is wrong — so pin them together here rather than letting a
    later rule drift.
    """
    declared = {rid for rid, r in REGISTRY.items()
                if r.fix_safety == engine_mod.FIX_SAFE}
    assert declared == transform.POLISH_RULES


def test_every_safe_rule_actually_offers_a_replacement():
    doc = Document.from_text(
        "It is important to note that we utilize the the model in order to "
        "perform an estimation of the rate, which is absolutely essential.",
        "plain")
    for s in check(doc, NLP, show_preferences=True):
        if s.fix_safety == engine_mod.FIX_SAFE:
            assert s.replacement is not None, \
                f"{s.rule_id} is marked safe but has no fix to apply"


def test_correction_tiers_are_declared_on_the_commodity_rules():
    assert REGISTRY["S001"].tier == engine_mod.TIER_SPELLING
    assert REGISTRY["LT001"].tier == engine_mod.TIER_GRAMMAR
    # GEC001 (2026-08-14): the learned tier's single entry point — an
    # abstaining scaffold until a local model ships, but its tier claim is
    # real (test_gec.py pins the abstention + offset-safety contract)
    assert REGISTRY["GEC001"].tier == engine_mod.TIER_GEC
    # everything else is craft or lens, never a correction tier
    for rid, r in REGISTRY.items():
        if rid not in ("S001", "LT001", "GEC001"):
            assert r.tier not in engine_mod.CORRECTION_TIER_PRIORITY, \
                f"{rid} claims a correction tier it does not implement"


def test_hidden_preference_count_is_gone():
    """It re-ran the whole pipeline to count what the first pass had seen."""
    assert not hasattr(engine_mod, "hidden_preference_count")
