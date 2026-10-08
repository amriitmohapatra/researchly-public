"""Figures, tables and the text that cites them (S2b, owner decision P4).

The file adapters record what a document contains (`Document.structure`):
LaTeX floats with their `\\label`, captions, `\\ref`s and equations; Word
captions, drawings and tables. This module turns that into two lists the
structural rules read:

- `floats(doc)`: each figure and table with its number, label, caption and
  span. LaTeX numbers floats in source order (per chapter when the document
  has chapters); a Word float is numbered by its caption ("Table 2. ...").
- `mentions(doc)`: each place the text cites one: a `\\ref{fig:x}` or a
  written "Figure 3", "Fig. 2b", "Tables 1-3". Mentions inside captions and
  tables are kept apart: a caption that says "as in Figure 1" is not where
  the reader is sent to look.

Supplementary and appendix items ("Figure S1", "Table A2") live in another
file, so they are never matched against this document's floats.

Plain text has no reliable structure (a PDF's "Figure 2.3" line may be a
caption, a list-of-figures entry or a running header), so it gets none: the
structural rules stay silent rather than guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .document import Document, StructureItem

KINDS = ("figure", "table")

# "Figure 3", "Fig. 2b", "Figs 1-3", "Figures 2 and 4", "Table 1", "Tables
# S1, S2". The number list stops at the first thing that is not a number.
# "Table A.4": an appendix lettered A, as economics papers and many theses
# number them (P33).
_NUM = r"(?:[A-Z]\.\d+|[SA]\d+|\d+(?:\.\d+)?)[a-z]?"
# A lettered appendix is stored like a chapter numbered above any real one,
# so "A.4" sorts and groups like "2.4": (LETTERED + 0, 4).
LETTERED = 100


def number_text(number: tuple | None) -> str:
    """(2, 4) -> "2.4"; (LETTERED, 4) -> "A.4"."""
    if not number:
        return "?"
    return ".".join(chr(ord("A") + x - LETTERED) if i == 0 and x >= LETTERED
                    else str(x) for i, x in enumerate(number))
_MENTION = re.compile(
    r"\b(Fig(?:ure)?s?\.?|Tables?)~?\s*"
    rf"({_NUM}(?:\s*(?:,|and|&|–|—|-|to)\s*{_NUM})*)")
_PART = re.compile(rf"{_NUM}|–|—|-|to\b")
_CAPTION_PREFIX = re.compile(
    rf"\s*(Fig(?:ure)?\.?|Table)\s*({_NUM})\s*[.:|\-–—]?\s*", re.IGNORECASE)


@dataclass
class Float:
    kind: str                         # figure | table
    number: tuple | None              # (3,) or (2, 3) for chapter 2
    start: int
    end: int
    label: str | None = None
    caption: StructureItem | None = None
    # In an appendix or supplement: cited from anywhere, in any order.
    appendix: bool = False

    @property
    def name(self) -> str:
        return f"{self.kind.capitalize()} {number_text(self.number)}"


@dataclass
class Mention:
    kind: str                         # figure | table | other (a \\ref)
    numbers: tuple                    # numbers cited, () for a bare \\ref
    start: int
    end: int
    label: str | None = None          # the \\ref key, when there is one
    in_caption: bool = False
    supplementary: bool = False


@dataclass
class Structure:
    floats: list = field(default_factory=list)
    mentions: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)   # \\label -> kind

    def resolve(self, key: str) -> str | None:
        """The label a \\ref key names: itself, or with the prefix a
        style's \\figref adds out of sight ("x" -> "fig:x")."""
        if key in self.labels:
            return key
        return next((p + key for p in _PREFIXES if p + key in self.labels),
                    None)

    def float_for(self, m: Mention):
        """The float a mention cites, or None (a supplementary item, an
        equation or section \\ref, or a number with no float)."""
        if m.label is not None:
            key = self.resolve(m.label)
            return next((f for f in self.floats if f.label == key), None)
        for f in self.floats:
            if f.kind == m.kind and f.number in m.numbers:
                return f
        return None


def _parse_number(text: str) -> tuple | None:
    text = re.sub(r"[a-z]$", "", text)            # "2b": panel b of 2
    lettered = re.fullmatch(r"([A-Z])\.(\d+)", text)
    if lettered:
        return (LETTERED + ord(lettered.group(1)) - ord("A"),
                int(lettered.group(2)))
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    return tuple(int(x) for x in text.split("."))


def _numbers(listing: str) -> tuple[tuple, bool]:
    """Numbers named in "1, 3-5 and 7" (ranges expanded); and whether any
    is supplementary ("S1", "A2")."""
    out: list[tuple] = []
    supplementary = False
    parts = _PART.findall(listing)
    i = 0
    while i < len(parts):
        p = parts[i]
        if p[0] in "SA" and not p[1:2] == ".":
            supplementary = True
        else:
            n = _parse_number(p)
            if n is not None:
                if (out and i >= 1 and parts[i - 1] in ("–", "—", "-", "to")
                        and len(n) == len(out[-1]) == 1 and n[0] > out[-1][0]
                        and n[0] - out[-1][0] < 50):
                    out += [(k,) for k in range(out[-1][0] + 1, n[0] + 1)]
                else:
                    out.append(n)
        i += 1
    return tuple(out), supplementary


_APPENDIX = re.compile(r"\\appendix\b")


def _in_appendix(doc: Document, pos: int) -> bool:
    if doc.section_at(pos) == "appendix":
        return True
    if doc.kind == "latex":
        src = doc.original
        for m in _APPENDIX.finditer(src, 0, pos):
            line = src[src.rfind("\n", 0, m.start()) + 1:m.start()]
            if not _COMMENTED.search(line):
                return True
    return False


def _kind_of(word: str) -> str:
    return "table" if word.lower().startswith("tab") else "figure"


def analyse(doc: Document) -> Structure:
    """Floats and mentions for a LaTeX or Word document; empty otherwise."""
    if doc.kind == "latex":
        return _latex(doc)
    if doc.kind == "word":
        return _word(doc)
    return Structure()


# --- LaTeX -------------------------------------------------------------------

def _latex(doc: Document) -> Structure:
    st = Structure()
    items = doc.structure
    src = doc.original
    chapters = sorted(h.start for h in doc.headings if h.level == 0)
    captions = [i for i in items if i.kind == "caption"]

    def captionof_kind(c) -> str | None:
        m = _CAPTIONOF.match(src, c.start)
        return m.group(1) if m else None

    def is_main(c) -> bool:
        # Not \\captionof (its own float), nor \\caption*, which prints
        # without a number.
        return (src.startswith("\\caption", c.start)
                and not src.startswith(("\\captionof", "\\caption*",
                                        "\\captionsetup"), c.start))

    # A float is an environment with a \caption, or a \captionof{figure}
    # anywhere (side-by-side minipages): numbered in order, per chapter.
    found = []
    for it in items:
        if it.kind in KINDS:
            # Panels (subfigure, minipage) carry their own \\caption: the
            # float's is the one sharing its \\label, else the last.
            inside = [c for c in captions
                      if it.start <= c.start < it.end and is_main(c)]
            cap = next((c for c in inside if it.label and c.label == it.label),
                       inside[-1] if inside else None)
            found.append((it.start, it.kind, it, cap))
    for c in captions:
        kind = captionof_kind(c)
        if kind in KINDS:
            found.append((c.start, kind,
                          StructureItem(kind, c.start, c.end, c.label), c))
    counters: dict = {}
    for _, kind, it, cap in sorted(found, key=lambda x: x[0]):
        number = None
        if cap is not None:
            chapter = sum(1 for c in chapters if c < it.start)
            key = (kind, chapter)
            counters[key] = counters.get(key, 0) + 1
            number = ((chapter, counters[key]) if chapters
                      else (counters[key],))
        label = it.label or (cap.label if cap is not None else None)
        st.floats.append(Float(kind, number, it.start, it.end, label, cap,
                               appendix=_in_appendix(doc, it.start)))

    # Every \label, wherever it is (an align, an algorithm, a section), so a
    # \ref to it is never taken for a broken one.
    for m in _LABEL.finditer(src):
        line = src[src.rfind("\n", 0, m.start()) + 1:m.start()]
        if not _COMMENTED.search(line):
            st.labels.setdefault(m.group(1).strip(), "other")
    for f in st.floats:
        if f.label:
            st.labels[f.label] = f.kind
    for it in items:
        if it.kind == "equation" and it.label:
            st.labels[it.label] = "equation"

    cap_spans = [(c.start, c.end) for c in captions]
    refs = []
    for it in items:
        if it.kind == "ref":
            kind = st.labels.get(st.resolve(it.label or "") or "", "other")
            refs.append(Mention(
                kind, (), it.start, it.end, it.label,
                in_caption=any(a <= it.start < b for a, b in cap_spans)))
    st.mentions = refs + _ranges(st, refs, doc.masked)
    # Written mentions too ("Figure 2" typed by hand, as pandoc and many
    # converters emit): matched by number, never by label.
    st.mentions += _written(doc, cap_spans, [(f.start, f.end) for f in
                                             st.floats if f.kind == "table"])
    st.mentions.sort(key=lambda m: m.start)
    return st


_PREFIXES = ("fig:", "tab:", "sec:", "eq:", "eqn:", "app:", "alg:",
             "fig-", "tab-", "sec-", "eq-")
_CAPTIONOF = re.compile(r"\\captionof\s*\{(figure|table)\}")
_LABEL = re.compile(r"\\label\s*\{([^{}]+)\}")
_COMMENTED = re.compile(r"(?<!\\)%")
_RANGE_SEP = re.compile(r"\s*(?:-{1,3}|–|—|to)\s*$")


def _ranges(st: Structure, refs: list, masked: str) -> list:
    """`Figures~\\ref{a}--\\ref{b}` cites everything between a and b."""
    out = []
    for x, y in zip(refs, refs[1:]):
        if not _RANGE_SEP.match(masked[x.end:y.start]):
            continue
        fx, fy = st.float_for(x), st.float_for(y)
        if (fx is None or fy is None or fx.kind != fy.kind
                or fx.number is None or fy.number is None
                or fx.number[:-1] != fy.number[:-1]):
            continue
        lo, hi = fx.number[-1], fy.number[-1]
        between = tuple(fx.number[:-1] + (k,) for k in range(lo + 1, hi))
        if between:
            out.append(Mention(fx.kind, between, x.start, y.end,
                               in_caption=x.in_caption))
    return out


# --- Word ---------------------------------------------------------------------

def _distinct_captions(doc: Document, captions: list) -> list:
    """One caption per float. A typed caption repeating the number of a
    styled one, or of a later typed one (a list of figures, a caption
    repeated on a continuation page), is not a second float (P33)."""
    def key(c):
        m = _CAPTION_PREFIX.match(doc.original, c.start, c.end)
        return (_kind_of(m.group(1)), m.group(2)) if m else None
    captions = [c for c in captions          # "Table 3 (continued)"
                if not _CONTINUED.search(doc.original, c.start, c.end)]
    styled = {key(c) for c in captions if c.label != "typed"}
    keep = []
    for i, c in enumerate(captions):
        k = key(c)
        if c.label == "typed" and k is not None and (
                k in styled or any(key(d) == k and d.label == "typed"
                                   for d in captions[i + 1:])):
            continue
        keep.append(c)
    return keep


def _own_table(tables, cap, captions, claimed):
    """The table this caption labels: the nearest unclaimed one within 400
    characters with no other caption in between."""
    def between(a: int, b: int) -> bool:
        return any(c is not cap and a <= c.start < b for c in captions)
    best, gap = None, (400, 0)
    for t in tables:
        if id(t) in claimed:
            continue
        if t.start >= cap.end:          # below the caption: preferred
            d = (t.start - cap.end, 0)
            clear = not between(cap.end, t.start)
        elif t.end <= cap.start:
            d = (cap.start - t.end, 1)
            clear = not between(t.end, cap.start)
        else:
            continue
        if clear and d < gap:
            best, gap = t, d
    return best


_CONTINUED = re.compile(r"\(?\bcont(?:inued|'d|\.)\)?\s*[.:]?\s*$",
                        re.IGNORECASE)


def _word(doc: Document) -> Structure:
    st = Structure()
    tables = [i for i in doc.structure if i.kind == "table"]
    if not tables:
        # The add-in sends table cells, not tables: join adjacent cells.
        for a, b in doc.table_spans:
            if tables and a - tables[-1].end <= 4:
                tables[-1].end = b
            else:
                tables.append(StructureItem("table", a, b))
    captions = _distinct_captions(doc, [i for i in doc.structure
                                        if i.kind == "caption"])
    claimed: set = set()
    for cap in captions:
        m = _CAPTION_PREFIX.match(doc.original, cap.start, cap.end)
        if not m:
            continue
        kind = _kind_of(m.group(1))
        number = _parse_number(m.group(2))
        if number is None:                          # "Figure S1": supplement
            continue
        start, end = cap.start, cap.end
        if kind == "table":
            # A table's caption sits just above (or below) its cells, with
            # no other caption between them: a table that is only an image
            # must not take the next table's cells (P33).
            near = _own_table(tables, cap, captions, claimed)
            if near is not None:
                claimed.add(id(near))
                start, end = min(start, near.start), max(end, near.end)
        st.floats.append(Float(kind, number, start, end, None, cap,
                               appendix=_in_appendix(doc, start)
                               or number[0] >= LETTERED))
    cap_spans = [(c.caption.start, c.caption.end) for c in st.floats]
    st.mentions = _written(doc, cap_spans, doc.table_spans)
    return st


def _written(doc: Document, cap_spans, table_spans) -> list[Mention]:
    out = []
    text = doc.masked
    for m in _MENTION.finditer(text):
        numbers, supplementary = _numbers(m.group(2))
        if not numbers and not supplementary:
            continue
        a = m.start()
        out.append(Mention(
            _kind_of(m.group(1)), numbers, a, m.end(),
            in_caption=any(x <= a < y for x, y in cap_spans),
            supplementary=supplementary and not numbers))
        if any(x <= a < y for x, y in table_spans):
            out.pop()                     # a table cell is not running text
    return out
