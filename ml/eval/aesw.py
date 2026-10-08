"""Parser for the AESW 2016 corpus (professionally edited scientific prose).

AESW is the closest thing that exists to Researchly's actual job: ~1.2M
sentences from 9,919 published journal articles, each shown before and
after a professional language editor worked on it. Every sentence therefore
comes with a free label — "an expert thought this needed changing" or "an
expert left it alone" — which is exactly the ground truth this project has
never had.

Markup:  <del>x</del><ins>y</ins>  substitution
         <ins>y</ins>              insertion
         <del>x</del>              deletion

Maths, citations and references arrive pre-substituted as _MATH_,
_MATHDISP_, _CITE_, _REF_, _CITE_TEXT_ … We translate those into ordinary
Markdown equivalents so Researchly's own masking layer handles them the way
it would in a real manuscript, rather than reading them as odd vocabulary.

Licence: CC BY-NC-SA 4.0 (VTeX), plus a no-de-anonymisation clause. Personal
and research use only — never redistribute derived text.
Cite: Vidas Daudaravicius (2016), AESW Data Set v1.2, VTeX.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

SENTENCE_RX = re.compile(r"<sentence[^>]*>(.*?)</sentence>", re.S)
TAG_RX = re.compile(r"<(del|ins)>(.*?)</\1>", re.S)

# AESW placeholders → markup Researchly already knows how to mask.
PLACEHOLDERS = [
    ("_MATHDISP_", "$$x$$"),
    ("_MATH_", "$x$"),
    ("_CITE_TEXT_", "[@ref]"),
    ("_CITE_", "[@ref]"),
    ("_REF_", "[@ref]"),
    ("_ABBR_", "ABBR"),
]


def _detokenize(s: str) -> str:
    """AESW is lightly tokenized; close the gaps that would look like typos."""
    s = re.sub(r"\s+([,.;:!?\)\]])", r"\1", s)
    s = re.sub(r"([\(\[])\s+", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _substitute(s: str) -> str:
    for token, repl in PLACEHOLDERS:
        s = s.replace(token, repl)
    return s


@dataclass
class Sentence:
    """One AESW sentence in both states, with the edit sites located."""
    before: str                       # what the author wrote
    after: str                        # what the editor published
    # (start, end) spans in `before` that the editor touched. An insertion
    # has zero width and is recorded as a 1-char span for overlap testing.
    edit_spans: list = field(default_factory=list)

    @property
    def was_edited(self) -> bool:
        return self.before != self.after


def parse_sentence(raw: str) -> Sentence:
    before_parts: list[str] = []
    after_parts: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0

    for m in TAG_RX.finditer(raw):
        plain = raw[pos:m.start()]
        before_parts.append(plain)
        after_parts.append(plain)
        kind, content = m.group(1), m.group(2)
        if kind == "del":
            start = sum(len(p) for p in before_parts)
            before_parts.append(content)
            spans.append((start, start + len(content)))
        else:
            start = sum(len(p) for p in before_parts)
            after_parts.append(content)
            spans.append((max(0, start - 1), start + 1))
        pos = m.end()

    tail = raw[pos:]
    before_parts.append(tail)
    after_parts.append(tail)

    before_raw = "".join(before_parts)
    after_raw = "".join(after_parts)

    # Detokenizing shifts offsets, so rescale the spans proportionally. Edit
    # sites are used for coarse "did we flag near here" overlap, not for
    # character-exact scoring, so approximate mapping is honest enough —
    # and it is stated here rather than implied.
    before = _substitute(_detokenize(before_raw))
    after = _substitute(_detokenize(after_raw))
    if before_raw and spans:
        scale = len(before) / len(before_raw)
        spans = [(int(a * scale), max(int(b * scale), int(a * scale) + 1))
                 for a, b in spans]

    return Sentence(before=before, after=after, edit_spans=spans)


def iter_sentences(path: Path, limit: int | None = None) -> Iterator[Sentence]:
    """Stream sentences without loading a 28 MB file into one string."""
    buf = ""
    seen = 0
    with open(path, encoding="utf-8") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), ""):
            buf += chunk
            last = 0
            for m in SENTENCE_RX.finditer(buf):
                s = parse_sentence(m.group(1))
                last = m.end()
                if len(s.before.split()) < 4:
                    continue          # fragments, headings, formula-only
                yield s
                seen += 1
                if limit and seen >= limit:
                    return
            buf = buf[last:]
