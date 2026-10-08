"""Local GEC (grammatical error correction) tier — SCAFFOLD.

This is the W3 Tier-B learned layer: a GECToR-style *token-level edit
tagger* that proposes minimal keep/delete/replace/append edits against the
source text. It is permitted by the amended non-negotiable #1 (local,
non-generative, confidence-scored, never auto-applied, `tier="gec"`),
and it is deliberately shipped OFF:

- no model weights ship with this build, so `available()` is False and the
  tier abstains completely;
- even with weights installed, the tier only runs when the user opts in
  with `[tiers] gec = true` in config — `None` (the default) means off for
  a learned tier, unlike the deterministic tiers where None means
  "use if available". A learned layer earns trust by being asked for.

Reproducibility contract (enforced by tests once a real model lands):

- weights + tokenizer are pinned by content (`MODEL_VERSION` names the
  exact artifact, and every suggestion records it in `source`);
- CPU inference, deterministic flags, no sampling — same text in, same
  edits out;
- edits below `CONFIDENCE_THRESHOLD` are dropped (abstention beats noise:
  precision over recall is architectural here, see CLAUDE.md #5);
- edits are expressed as offsets into the ORIGINAL text and are dropped if
  they touch a masked span (math, code, citations) — the same offset-safety
  rule every other tier obeys.

The scaffold has no ML dependency and never downloads anything. A future
model plugs in by implementing `EditBackend.predict` and dropping pinned
weights into MODEL_DIR; nothing else changes. NO cloud API may ever be
wired here — if a capable local model cannot be found, this tier stays an
abstaining scaffold (user decision, 2026-08-14).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Names the exact model artifact a build ships. The scaffold ships none.
MODEL_VERSION = "gec-scaffold-0 (no model installed)"

# Where pinned weights would live. Deliberately under ~/.researchly so the
# engine package stays small and the artifact is user-inspectable.
MODEL_DIR = Path.home() / ".researchly" / "models" / "gec"

# Edits scoring below this are dropped. Chosen conservatively; must be
# re-derived from a labelled corpus before a real model ships (the AESW
# recall baseline to beat is 15.3% — see PROJECT_LOG P18).
CONFIDENCE_THRESHOLD = 0.8

# Cap on how much of a sentence one edit may replace. A token-level tagger
# proposing to rewrite a whole clause has left "minimal edit" territory and
# is generating — which is forbidden. Belt-and-braces against a future
# backend misbehaving.
MAX_EDIT_CHARS = 40


@dataclass
class Edit:
    """One minimal token-level edit, in ORIGINAL-text offsets."""
    start: int
    end: int
    replacement: str          # "" means delete
    confidence: float
    message: str = ""         # short human label, e.g. "subject-verb"

    def is_sane(self) -> bool:
        return (0 <= self.start <= self.end
                and (self.end - self.start) <= MAX_EDIT_CHARS
                and len(self.replacement) <= MAX_EDIT_CHARS)


class EditBackend:
    """Interface a real local tagger implements. The scaffold has none.

    Tests inject a fake via `set_backend()` to pin the wiring (offset
    safety, masking, thresholds, config gating) without any ML dependency.
    """

    #: identifies the model in suggestion provenance
    version: str = MODEL_VERSION

    def predict(self, text: str) -> list[Edit]:  # pragma: no cover
        raise NotImplementedError


_BACKEND: Optional[EditBackend] = None
_BACKEND_EXPLICIT = False       # a test/dev injected one (may be None)


def set_backend(backend: Optional[EditBackend]) -> None:
    """Inject or clear the backend (tests; future model loader)."""
    global _BACKEND, _BACKEND_EXPLICIT
    _BACKEND = backend
    _BACKEND_EXPLICIT = backend is not None


def get_backend() -> Optional[EditBackend]:
    """The live backend, or None — in which case the tier abstains.

    The scaffold never auto-loads anything: no weights are shipped, and
    probing MODEL_DIR for a future artifact is the *loader's* job once one
    exists. Returning None here is the abstention path.
    """
    return _BACKEND


def available() -> bool:
    """Can this tier produce edits right now?"""
    return _BACKEND is not None


def model_installed() -> bool:
    """Are pinned weights present on disk? (Scaffold: looks, never loads.)"""
    try:
        return (MODEL_DIR / "PINNED").exists()
    except Exception:
        return False


def predict_edits(text: str) -> list[Edit]:
    """Confidence-filtered, sanity-checked edits — or [] (abstain).

    Never raises: a learned tier that can crash a check is worse than one
    that stays silent, because every other tier dies with it.
    """
    backend = get_backend()
    if backend is None:
        return []
    try:
        edits = backend.predict(text)
    except Exception:
        return []
    out = []
    for e in edits:
        if not isinstance(e, Edit):
            continue
        if not e.is_sane():
            continue
        if e.confidence < CONFIDENCE_THRESHOLD:
            continue
        out.append(e)
    return out
