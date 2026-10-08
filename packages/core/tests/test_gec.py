"""Golden-output tests for the GEC scaffold (W3 Tier B, sprint item 8).

The scaffold ships no model, so the *behaviour under absence* is the
product: total abstention, honest health reporting, opt-in gating, and —
via an injected fake backend — offset safety identical to every other
tier. These tests are the contract a real local model must satisfy before
it ships; none of them require any ML dependency.
"""

import pytest

from researchly import api
from researchly import config as config_mod
from researchly import gec
from researchly.document import Document
from researchly.engine import Category, REGISTRY, check
from researchly.gec import Edit, EditBackend

NLP = api.get_nlp()

TEXT = ("The results was significant. The model $R_0 = 2.3$ were fitted "
        "to the data.")


@pytest.fixture(autouse=True)
def clean_backend():
    """Every test starts and ends scaffold-pure (no backend)."""
    gec.set_backend(None)
    yield
    gec.set_backend(None)


class FakeBackend(EditBackend):
    version = "fake-gector-test-1"

    def __init__(self, edits):
        self._edits = edits

    def predict(self, text):
        return self._edits


def _gec_suggestions(text, kind="plain", **overrides):
    cfg = config_mod.Config().with_overrides(**overrides)
    a = api.analyze(text, kind=kind, nlp=NLP, cfg=cfg)
    return [s for s in a.suggestions if s.tier == "gec"]


# --- golden: abstention ----------------------------------------------------

def test_no_backend_means_total_abstention():
    """GOLDEN: scaffold build, tier enabled — still zero GEC suggestions."""
    assert _gec_suggestions(TEXT, gec_tier=True) == []


def test_default_config_keeps_the_tier_off_even_with_a_backend():
    """GOLDEN: opt-in gating. A live backend without `gec = true` is inert."""
    gec.set_backend(FakeBackend([Edit(4, 15, "results were", 0.99)]))
    assert _gec_suggestions(TEXT) == []                 # gec_tier=None
    assert _gec_suggestions(TEXT, gec_tier=False) == []


def test_predict_edits_abstains_below_confidence_threshold():
    gec.set_backend(FakeBackend([
        Edit(4, 11, "results", 0.10),                   # below threshold
        Edit(4, 11, "result", gec.CONFIDENCE_THRESHOLD - 0.01),
    ]))
    assert gec.predict_edits(TEXT) == []


def test_a_crashing_backend_abstains_rather_than_failing_the_check():
    class Exploding(EditBackend):
        version = "boom"

        def predict(self, text):
            raise RuntimeError("model corrupted")

    gec.set_backend(Exploding())
    assert gec.predict_edits(TEXT) == []
    assert _gec_suggestions(TEXT, gec_tier=True) == []


def test_health_reports_the_scaffold_honestly():
    from researchly.health import engine_status
    tiers = {t.tier: t for t in engine_status(config_mod.Config())}
    g = tiers["gec"]
    assert not g.ok
    assert g.state == "missing"
    assert "abstains" in g.detail

    gec.set_backend(FakeBackend([]))
    g2 = {t.tier: t for t in engine_status(config_mod.Config())}["gec"]
    assert not g2.ok and g2.state == "disabled"     # present but opt-in

    cfg_on = config_mod.Config().with_overrides(gec_tier=True)
    g3 = {t.tier: t for t in engine_status(cfg_on)}["gec"]
    assert g3.ok and g3.state == "ready"
    assert "fake-gector-test-1" in g3.detail


# --- golden: offset safety -------------------------------------------------

MD = ("The results was significant.\n\n"
      "The rate $\\lambda_i$ were estimated from `fit_model()` output "
      "[@smith2020].\n")


def test_edits_map_to_original_text_offsets():
    """GOLDEN: an accepted edit's span reads the same in original text."""
    start, end = MD.index("was"), MD.index("was") + 3
    gec.set_backend(FakeBackend([Edit(start, end, "were", 0.95,
                                      "subject-verb agreement")]))
    # LT001 flags the same agreement error and outranks GEC in overlap
    # resolution (that ranking has its own test below) — isolate it here.
    out = _gec_suggestions(MD, kind="markdown", gec_tier=True,
                           disabled=["LT001", "S001"])
    assert len(out) == 1
    s = out[0]
    assert (s.start, s.end) == (start, end)
    assert s.text == "was"                    # engine slices ORIGINAL text
    assert s.replacement == "were"
    assert s.category is Category.CORRECTION
    assert s.fix_safety == "review"           # never bulk/auto-applied
    assert 0 < s.confidence <= 1


def test_edits_inside_masked_spans_are_dropped():
    """GOLDEN: math, code and citations are untouchable."""
    math_at = MD.index("\\lambda_i")
    code_at = MD.index("fit_model")
    cite_at = MD.index("@smith2020")
    gec.set_backend(FakeBackend([
        Edit(math_at, math_at + 9, "lambda", 0.99),
        Edit(code_at, code_at + 9, "fitModel", 0.99),
        Edit(cite_at, cite_at + 10, "@smith2021", 0.99),
    ]))
    assert _gec_suggestions(MD, kind="markdown", gec_tier=True) == []


def test_edits_straddling_a_mask_boundary_are_dropped():
    """An edit covering prose AND masked markup would splice mask-derived
    text into the source — the exact bug that once made Polish eat inline
    math. The span check must compare masked vs original, not just strip."""
    start = MD.index("rate $")               # covers "rate $\lambda_i$"
    end = MD.index("$ were") + 1
    gec.set_backend(FakeBackend([Edit(start, end, "estimated rate", 0.99)]))
    assert _gec_suggestions(MD, kind="markdown", gec_tier=True) == []


def test_insertions_at_masked_boundaries_are_dropped():
    inside_math = MD.index("\\lambda_i") + 2      # insertion point in math
    gec.set_backend(FakeBackend([Edit(inside_math, inside_math, "x", 0.99)]))
    assert _gec_suggestions(MD, kind="markdown", gec_tier=True) == []


def test_oversized_edits_are_rejected_as_generation():
    """A 'minimal edit' longer than MAX_EDIT_CHARS is generation in
    disguise and must be refused at the sanity gate."""
    big = "x" * (gec.MAX_EDIT_CHARS + 1)
    gec.set_backend(FakeBackend([Edit(0, 3, big, 0.99)]))
    assert gec.predict_edits(TEXT) == []


# --- wiring ---------------------------------------------------------------

def test_gec001_is_registered_with_the_right_provenance():
    api.ensure_rules_loaded()
    r = REGISTRY["GEC001"]
    assert r.tier == "gec"
    assert r.fix_safety == "review"
    assert r.category is Category.CORRECTION


def test_gec_is_never_in_the_bulk_polish_set():
    """fix_safety='review' must keep GEC out of transform.POLISH_RULES."""
    from researchly import transform
    assert "GEC001" not in getattr(transform, "POLISH_RULES", set())


def test_suggestion_records_the_model_version():
    start, end = MD.index("was"), MD.index("was") + 3
    gec.set_backend(FakeBackend([Edit(start, end, "were", 0.91)]))
    out = _gec_suggestions(MD, kind="markdown", gec_tier=True,
                           disabled=["LT001", "S001"])
    assert out and "fake-gector-test-1" in out[0].message


def test_overlap_resolution_prefers_explainable_tiers_over_gec():
    """S001/LT001 carry a named, teachable rule; the tagger is the fallback.
    When both fire on one span, the deterministic tier must win."""
    text = "The subsceptible population was large."
    start = text.index("subsceptible")
    gec.set_backend(FakeBackend([
        Edit(start, start + len("subsceptible"), "susceptible", 0.99)]))
    cfg = config_mod.Config().with_overrides(gec_tier=True)
    a = api.analyze(text, nlp=NLP, cfg=cfg)
    over = [s for s in a.suggestions
            if s.start < start + 12 and s.end > start]
    tiers = {s.tier for s in over}
    if "spelling" in tiers or "grammar" in tiers:
        assert "gec" not in tiers
