"""GEC001 — the learned-correction tier's single engine rule.

All GECToR-style edits enter the pipeline through this one rule so their
provenance is auditable: every suggestion is `tier="gec"`,
`fix_safety="review"` (never bulk-applied, never auto-applied), carries a
per-edit confidence, and records the exact model version in `source`.

Gating, in order:

1. `cfg.gec_tier is True` — the learned tier is OPT-IN. `None` (default)
   means off; this inverts the deterministic tiers' "use if available"
   default on purpose (see gec.py docstring).
2. `gec.available()` — no backend, no edits: total abstention.
3. Offset safety — an edit that touches a masked span (math, code,
   citations, headings) is dropped, and the replacement text check uses the
   ORIGINAL text, never the mask (the Polish-ate-my-math lesson,
   AGENTS.md conventions).
4. Confidence — already filtered in gec.predict_edits, re-checked here.
"""

from __future__ import annotations

from . import gec
from .document import Document
from .engine import Category, Suggestion, TIER_GEC, rule


@rule("GEC001", "learned-correction", Category.CORRECTION,
      "Minimal token-level edits from a local learned tagger (opt-in).",
      'A local, non-generative edit tagger proposing minimal corrections '
      'the deterministic tiers cannot express. It runs entirely on this '
      'machine, is off unless you enable it in settings, scores every '
      'edit, and abstains below a confidence threshold. Its suggestions '
      'are never applied automatically and never included in bulk Polish.',
      plain=('A small correction from a model that runs on this computer only. '
             'It never writes new text; it proposes a tiny edit and says how '
             'sure it is. It is off unless you turn it on, and it never changes '
             'anything by itself.'),
      source="local GEC",
      tier=TIER_GEC, fix_safety="review")
def gec001_learned_corrections(doc, document: Document):
    cfg = getattr(document, "config", None)
    # Opt-in: only an explicit True runs the learned tier.
    if cfg is None or cfg.gec_tier is not True:
        return
    backend = gec.get_backend()
    if backend is None:
        return                                     # abstain
    for e in gec.predict_edits(document.original):
        start, end = e.start, e.end
        if end > len(document.original):
            continue
        # Never flag inside (or across) a masked region. Masked chars are
        # spaces; a span is unsafe if any original char it covers was
        # masked away.
        span_masked = document.masked[start:end]
        span_original = document.original[start:end]
        if start == end:
            # pure insertion: unsafe if the insertion point is inside a
            # masked region (the char before or after was masked away)
            before = document.masked[max(0, start - 1):start]
            after = document.masked[start:start + 1]
            before_o = document.original[max(0, start - 1):start]
            after_o = document.original[start:start + 1]
            if (before != before_o) or (after != after_o):
                continue
        elif span_masked != span_original:
            continue
        if not span_original.strip() and start != end:
            continue                               # whitespace-only span
        label = e.message or "learned correction"
        yield Suggestion(
            message=(f"{label} (confidence "
                     f"{e.confidence:.2f}, {backend.version})"),
            start=start, end=end,
            replacement=e.replacement,
            confidence=e.confidence,
        )
