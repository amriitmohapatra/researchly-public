"""Compatibility path: the argument model moved to `researchly.discourse`
(S4, 2026-10-08). Import from there; this module re-exports it."""

from .discourse.argument import *  # noqa: F401,F403
from .discourse.argument import (ArgumentObject, SentenceRole,  # noqa: F401
                                 build_argument, label_sentence,
                                 label_sentences, summarize)
