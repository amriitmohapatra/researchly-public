"""The narrative map (S4): per section, which moves are present, missing
or out of order; the argument's missing links; and the hedging trajectory.

Built from the same parse as the suggestions (`api.analyze(...,
with_narrative=True)`), so a document is analysed once. Everything here is
deterministic and traceable: a present move names the sentence it rests
on, a missing one carries the authored question, its lesson and a
fill-in frame, and nothing is a score.
"""

from __future__ import annotations

import re
from typing import Optional

from .. import learn
from .. import lexicons as lx
from .. import sources
from ..document import Document
from . import argument as argument_mod
from .moves import MOVES, ORDERED, SCHEMAS, SECTION_LABELS, label_moves

SOURCE = sources.cite("Swales+WW+§2")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][\w'-]*")
# Clean enough to quote back as evidence.
_EVIDENCE_CHARS = 180


def _sentences(document: Document, spacy_doc=None) -> list:
    """(start, end, text) of each prose sentence, in order, from the masked
    text (so offsets survive markup); table cells skipped."""
    out = []
    if spacy_doc is not None:
        for sent in spacy_doc.sents:
            text = sent.text.strip()
            if text and not document.in_table(sent.start_char):
                out.append((sent.start_char, sent.end_char, text))
        return out
    text = document.masked
    pos = 0
    for chunk in _SENT_SPLIT.split(text):
        stripped = chunk.strip()
        if not stripped:
            pos += len(chunk) + 1
            continue
        start = text.find(chunk, pos)
        start = pos if start == -1 else start
        pos = start + len(chunk)
        if not document.in_table(start):
            out.append((start, start + len(chunk), stripped))
    return out


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _EVIDENCE_CHARS else text[:_EVIDENCE_CHARS - 1].rstrip() + "…"


def _move_entry(move_id: str, status: str, evidence: Optional[str] = None,
                note: str = "", section: str = "") -> dict:
    m = MOVES[move_id]
    return {
        "id": m.id, "label": m.label, "status": status,
        "question": m.question, "plain": m.plain, "frame": m.frame,
        "source": m.citation, "evidence": evidence, "note": note,
        "learn_ref": learn.card_for_move(section, m.id),
    }


def _section_map(section: str, sents: list) -> dict:
    schema = SCHEMAS[section]
    first: dict = {}          # move -> index of its first sentence
    evidence: dict = {}
    for i, (_, _, text) in enumerate(sents):
        for mid in label_moves(text, section, first=(i == 0)):
            if mid not in first:
                first[mid] = i
                evidence[mid] = _quote(text)
    out = []
    misplaced = _misplaced(schema, first) if section in ORDERED else set()
    for j, mid in enumerate(schema):
        if mid not in first:
            out.append(_move_entry(mid, "missing", section=section))
            continue
        status, note = "present", ""
        if mid in misplaced:
            status = "out_of_order"
            after = [schema[i] for i in range(j + 1, len(schema))
                     if schema[i] in first and first[schema[i]] < first[mid]]
            before = [schema[i] for i in range(j) if schema[i] in first
                      and first[schema[i]] > first[mid]]
            if after:
                note = "Appears after " + MOVES[after[-1]].label.lower() + "."
            elif before:
                note = "Appears before " + MOVES[before[0]].label.lower() + "."
        out.append(_move_entry(mid, status, evidence[mid], note, section))
    present = sum(1 for e in out if e["status"] != "missing")
    return {
        "section": section,
        "label": SECTION_LABELS.get(section, section.capitalize()),
        "sentences": len(sents),
        "words": sum(len(_WORD.findall(t)) for _, _, t in sents),
        "moves": out,
        "present": present,
        "expected": len(schema),
    }


def _misplaced(schema: tuple, first: dict) -> set:
    """The present moves that are out of place: those not on the longest
    run of moves that appear in the expected order, so one misplaced
    sentence is reported once, not as every move around it."""
    present = [m for m in schema if m in first]
    idx = [first[m] for m in present]
    n = len(idx)
    if n < 2:
        return set()
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if idx[j] < idx[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(n), key=lambda i: best[i])
    keep = set()
    while end != -1:
        keep.add(present[end])
        end = prev[end]
    return set(present) - keep


# Missing links worth a line on the map: where the argument is made. A
# Results section shows data without reading them by design.
_LINK_SECTIONS = frozenset({"abstract", "introduction", "discussion",
                            "limitations", "conclusion"})


def _hedging(by_section: dict, order: list) -> list:
    out = []
    for section in order:
        sents = by_section[section]
        words = hedges = boosters = 0
        for _, _, text in sents:
            for w in _WORD.findall(text):
                words += 1
                low = w.lower()
                if low in lx.HEDGE_TOKENS:
                    hedges += 1
                elif low in lx.BOOSTER_TOKENS:
                    boosters += 1
        if words == 0:
            continue
        h, b = hedges * 100.0 / words, boosters * 100.0 / words
        out.append({
            "section": section,
            "label": SECTION_LABELS.get(section, section.capitalize()),
            "words": words,
            "hedges_per_100w": round(h, 2),
            "boosters_per_100w": round(b, 2),
            "reading": _reading(h, b),
        })
    return out


def _reading(h: float, b: float) -> str:
    """A phrase, never a score: how the section's confidence reads."""
    if h == 0 and b == 0:
        return "flat"
    if b == 0:
        return "hedged"
    if h == 0:
        return "assertive"
    ratio = h / b
    if ratio >= 3:
        return "heavily hedged"
    if ratio <= 1 / 3:
        return "assertive"
    return "balanced"


def build_narrative(document: Document, spacy_doc=None,
                    profile=None) -> dict:
    """The map every surface renders.

    {"sections": [...], "unmapped": [...], "missing_links": [...],
     "hedging": [...], "note": str, "source": str}
    """
    sents = _sentences(document, spacy_doc)
    by_section: dict = {}
    order: list = []
    for start, end, text in sents:
        section = document.section_at(start)
        if section not in by_section:
            by_section[section] = []
            order.append(section)
        by_section[section].append((start, end, text))

    sections = [_section_map(s, by_section[s]) for s in order
                if s in SCHEMAS]
    unmapped = [s for s in order if s not in SCHEMAS
                and s not in ("front", "references")]

    links = []
    for obj in argument_mod.build_argument(document, spacy_doc=spacy_doc):
        if obj.section not in _LINK_SECTIONS:
            continue
        for code, message in obj.missing_links:
            links.append({
                "section": obj.section,
                "label": SECTION_LABELS.get(obj.section, obj.section),
                "code": code,
                "message": message,
                "learn_ref": learn.card_for_link(code),
                "evidence": [_quote(document.original[a:b])
                             for a, b in obj.link_spans.get(code, [])[:3]],
                "source": sources.cite("WW+Toulmin+§4"),
            })

    if not sections:
        if not document.headings:
            note = ("No section headings were found, so there is no map "
                    "to draw. Add headings (Introduction, Methods, "
                    "Results, Discussion) or check a longer part of the "
                    "document.")
        else:
            note = ("The headings found are not the usual sections "
                    "(Introduction, Methods, Results, Discussion), so "
                    "there is no map to draw for them.")
    else:
        missing = sum(1 for s in sections for m in s["moves"]
                      if m["status"] == "missing")
        note = ("Every expected move is present." if missing == 0 else
                f"{missing} expected move{'s are' if missing != 1 else ' is'}"
                " missing; each one below has a question and a frame to "
                "fill in.")
    return {
        "sections": sections,
        "unmapped": unmapped,
        "missing_links": links,
        "hedging": _hedging(by_section, [s for s in order
                                         if s not in ("front", "references")]),
        "note": note,
        "profile": getattr(profile, "id", None),
        "source": SOURCE,
    }


def render_narrative(n: dict) -> str:
    """Plain-text map for the CLI."""
    marks = {"present": "present", "missing": "MISSING",
             "out_of_order": "out of order"}
    L: list[str] = []
    add = L.append
    add("NARRATIVE MAP")
    add(n["note"])
    for s in n["sections"]:
        add("")
        add(f"{s['label']} ({s['words']} words): {s['present']} of "
            f"{s['expected']} moves")
        for m in s["moves"]:
            line = f"   {m['label']:<26} {marks[m['status']]}"
            if m["note"]:
                line += f" ({m['note'].rstrip('.')})"
            add(line)
            if m["status"] == "missing":
                add(f"      {m['question']}")
                add(f"      frame: {m['frame']}")
            elif m["evidence"]:
                add(f'      "{m["evidence"]}"')
    if n["missing_links"]:
        add("")
        add("Argument: missing links")
        for link in n["missing_links"]:
            add(f"   [{link['label']}] {link['message']}")
    if n["hedging"]:
        add("")
        add("Hedging across the document (per 100 words)")
        for h in n["hedging"]:
            add(f"   {h['label']:<14} hedges {h['hedges_per_100w']:>5}  "
                f"boosters {h['boosters_per_100w']:>5}  {h['reading']}")
    add("")
    add("Source: " + n["source"])
    return "\n".join(L)
