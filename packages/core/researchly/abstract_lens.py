"""Compatibility path: the abstract lens moved to `researchly.discourse`
(S4, 2026-10-08). Import from there; this module re-exports it (the AB802
rule registers when the discourse module is imported)."""

from .discourse.abstract_lens import *  # noqa: F401,F403
from .discourse.abstract_lens import (FRAMES, MOVES, SIGNALS,  # noqa: F401
                                      ab802_abstract_completeness, analyze,
                                      missing_moves)
