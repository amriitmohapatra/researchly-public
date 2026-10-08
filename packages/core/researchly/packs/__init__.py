"""Discipline packs (S4, product decision P3): the reporting checklists of
a field, checked against the text.

A pack checks *reporting*, never the science: for each item of a published
reporting guideline it asks whether the text says the thing a reader of
that kind of study needs (the eligibility criteria, the forecast horizon,
how missing data were handled), and points to the sentence where it does.
It cannot tell whether the design was right, only whether it was reported.

Format: a `Pack` holds `Checklist`s; a checklist holds `Item`s. Each item
is an authored question in Researchly's own words (the guidelines are
cited, never quoted), a plain reason, the sections where readers look for
it, and the signals (regular expressions over one sentence) that find it.
An item the signals do not find is "needs your check", never "missing":
it may sit in a table, a figure or the supplement, or not apply (the
surfaces let the writer mark it so for the session; Codex review #6).

The first pack is epidemiology (`epidemiology.py`), the owner's field.
A new discipline is one more module listed in `PACKS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .. import sources


@dataclass(frozen=True)
class Item:
    id: str
    topic: str
    question: str
    plain: str
    signals: tuple
    sections: tuple = ()          # where readers look; empty = anywhere


@dataclass(frozen=True)
class Checklist:
    id: str
    label: str
    design: str                   # the kind of study it is for, in words
    source: str                   # a code for sources.cite
    cue: str                      # regex: the text looks like this design
    items: tuple

    @property
    def citation(self) -> str:
        return sources.cite(self.source)


@dataclass(frozen=True)
class Pack:
    id: str
    label: str
    checklists: tuple


def _packs() -> dict:
    from . import epidemiology
    return {p.id: p for p in (epidemiology.PACK,)}


def checklists() -> dict:
    """Every checklist of every pack, by id."""
    return {c.id: c for p in _packs().values() for c in p.checklists}


def listing() -> list:
    """For a selector: every checklist, with what it is for."""
    return [{"id": c.id, "label": c.label, "design": c.design,
             "pack": p.label}
            for p in _packs().values() for c in p.checklists]


def suggest(text: str) -> Optional[str]:
    """The checklist the text's own words point to, or None. The most
    specific design wins: a systematic review of trials is a review."""
    for cid in ("prisma", "consort", "epiforge", "strobe"):
        c = checklists().get(cid)
        if c is not None and re.search(c.cue, text, re.IGNORECASE):
            return cid
    return None


_QUOTE = 180


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _QUOTE else text[:_QUOTE - 1].rstrip() + "…"


def check(document, checklist_id: str, spacy_doc=None,
          suggested: Optional[str] = None) -> Optional[dict]:
    """Report each item of one checklist as reported (with its sentence) or
    not found. None for an unknown checklist."""
    c = checklists().get(checklist_id)
    if c is None:
        return None
    from ..discourse.narrative import _sentences
    sents = _sentences(document, spacy_doc)
    with_section = [(document.section_at(a), t) for a, _, t in sents]
    present = {s for s, _ in with_section}
    items = []
    for it in c.items:
        where = [s for s in it.sections if s in present]
        pool = [t for s, t in with_section if not where or s in where]
        hit = next((t for t in pool
                    if any(re.search(rx, t, re.IGNORECASE)
                           for rx in it.signals)), None)
        items.append({
            "id": it.id, "topic": it.topic, "question": it.question,
            "plain": it.plain, "sections": list(it.sections),
            "status": "reported" if hit else "needs_check",
            "evidence": _quote(hit) if hit else None,
        })
    reported = sum(1 for i in items if i["status"] == "reported")
    total = len(items)
    note = (f"{reported} of {total} items were found in the text. The "
            "others need your check: they may be reported in a table, a "
            "figure or the supplement, or not apply to this study. This "
            "checks reporting only, never the science."
            if reported < total else
            f"All {total} items were found in the text.")
    return {"id": c.id, "label": c.label, "design": c.design,
            "source": c.citation, "suggested": suggested == c.id,
            "items": items, "reported": reported, "total": total,
            "note": note}
