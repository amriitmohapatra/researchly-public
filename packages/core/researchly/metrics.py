"""M901 — document metrics: a read-out, not a score.

Deliberately NOT a gamified writing score (research/01 §4-AVOID: an overall
score incentivizes accepting everything and homogenizes prose). These are
descriptive dials the author interprets.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import lexicons as lx
from .document import Document


@dataclass
class Metrics:
    sentences: int = 0
    words: int = 0
    mean_sentence_len: float = 0.0
    long_sentences: int = 0            # > 40 words
    nominalizations_per_100w: float = 0.0
    hedges_per_100w: float = 0.0
    boosters_per_100w: float = 0.0     # Hyland metadiscourse meter
    self_mention_per_100w: float = 0.0
    passive_share_by_section: dict = field(default_factory=dict)

    @property
    def hedge_booster_balance(self) -> str:
        """Calibration read-out: 'confidence without cockiness'."""
        h, b = self.hedges_per_100w, self.boosters_per_100w
        if h == 0 and b == 0:
            return "flat (no hedges, no boosters)"
        if b == 0:
            return "hedge-only"
        if h == 0:
            return "booster-only"
        ratio = h / b
        if ratio >= 3:
            return f"hedge-heavy ({ratio:.1f}:1)"
        if ratio <= 1 / 3:
            return f"booster-heavy (1:{1 / ratio:.1f})"
        return f"balanced ({ratio:.1f}:1)"

    def to_dict(self) -> dict:
        return {
            "sentences": self.sentences,
            "words": self.words,
            "mean_sentence_len": round(self.mean_sentence_len, 1),
            "long_sentences": self.long_sentences,
            "nominalizations_per_100w": round(self.nominalizations_per_100w, 2),
            "hedges_per_100w": round(self.hedges_per_100w, 2),
            "boosters_per_100w": round(self.boosters_per_100w, 2),
            "self_mention_per_100w": round(self.self_mention_per_100w, 2),
            "hedge_booster_balance": self.hedge_booster_balance,
            "passive_share_by_section": self.passive_share_by_section,
        }


def compute(spacy_doc, document: Document) -> Metrics:
    m = Metrics()
    lengths: list[int] = []
    nominal = 0
    hedges = 0
    boosters = 0
    self_mentions = 0
    passive_sent = Counter()
    total_sent = Counter()

    for sent in spacy_doc.sents:
        toks = [t for t in sent if not t.is_punct and not t.is_space]
        if not toks:
            continue
        # Table cells are data, not prose. Counting them made a parameter
        # table look like a run of very short sentences and dragged the
        # mean-sentence-length read-out around.
        if document.in_table(sent.start_char):
            continue
        lengths.append(len(toks))
        section = document.section_at(sent.start_char)
        total_sent[section] += 1
        if any(t.dep_ == "auxpass" for t in sent):
            passive_sent[section] += 1
        for t in toks:
            low = t.text.lower()
            if (t.pos_ == "NOUN" and len(low) >= lx.NOMINAL_MIN_LEN
                    and low.endswith(lx.NOMINAL_SUFFIXES)
                    and low not in lx.NOMINAL_ALLOWLIST):
                nominal += 1
            if low in lx.HEDGE_TOKENS:
                hedges += 1
            if low in lx.BOOSTER_TOKENS:
                boosters += 1
            if low in lx.SELF_MENTION_TOKENS:
                self_mentions += 1

    m.sentences = len(lengths)
    m.words = sum(lengths)
    if lengths:
        m.mean_sentence_len = m.words / len(lengths)
        m.long_sentences = sum(1 for n in lengths if n > 40)
    if m.words:
        m.nominalizations_per_100w = 100 * nominal / m.words
        m.hedges_per_100w = 100 * hedges / m.words
        m.boosters_per_100w = 100 * boosters / m.words
        m.self_mention_per_100w = 100 * self_mentions / m.words
    m.passive_share_by_section = {
        sec: round(passive_sent[sec] / n, 2)
        for sec, n in total_sent.items() if n >= 3
    }
    return m
