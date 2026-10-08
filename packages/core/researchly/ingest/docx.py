"""Word .docx -> one Document, read the way the Word add-in reads it.

The body of `word/document.xml` is walked in order and turned into the same
`[{"text", "style", "kind"}]` paragraphs the add-in sends, then built with
`Document.from_word`, so a heading or a table cell behaves identically in an
upload and in Word itself.

What counts as text (what a reader of the final document sees):
- runs (`w:t`), tabs (`w:tab` -> "\\t"), breaks (`w:br`/`w:cr` -> "\\n");
- tracked changes as if accepted: insertions kept, deletions and
  moved-away text dropped;
- field results kept, field codes (`w:instrText`) dropped, so a Zotero or
  EndNote citation reads "(Smith 2020)", not its JSON;
- hidden text (`w:vanish`) dropped.

Headings come from paragraph styles, resolved through `word/styles.xml`:
Word stores built-in style NAMES in English ("heading 1", "Title") even when
the style id is localised, and a custom style is a heading when it (or a
style it is based on) has an outline level.

Structure: drawings and pictures -> figure (their paragraph); equations
(`m:oMath`) -> equation, replaced by a masked "[equation]" placeholder;
Caption-styled paragraphs -> caption; tables -> table over their cells.

Ignored in S2, silently: comments, footnotes and endnotes, headers and
footers, and text inside text boxes (it sits inside drawings).

XML is parsed with defusedxml with DTDs forbidden, so an entity bomb or an
external entity (XXE) is rejected rather than expanded or fetched.
"""

from __future__ import annotations

import re

from ..document import Document, Segment, StructureItem
from . import MAX_TEXT_CHARS, IngestError
from ._zip import open_zip, read_member

EQUATION = "[equation]"
_BLOCK_CONTAINERS = {"body", "tr", "tc", "sdt", "sdtContent", "customXml"}
# Never text: properties, deletions, field codes, note and comment marks,
# and the duplicate fallback rendering inside mc:AlternateContent.
_SKIP = {"pPr", "rPr", "sdtPr", "sdtEndPr", "del", "delText", "moveFrom",
         "instrText", "fldData", "footnoteReference", "endnoteReference",
         "commentReference", "Fallback"}
_FALSE = {"0", "false", "off"}


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attr(el, name: str):
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return None


def _child(el, name: str):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _parse(data: bytes):
    try:
        import defusedxml.ElementTree as DET
        from defusedxml import DefusedXmlException
    except ImportError:
        # Never fall back to the standard library parser: it expands
        # entities. health.py reports the missing package with its remedy.
        raise IngestError("unsupported_file",
                          "Reading .docx files is not available on this "
                          "installation (a component is missing).") from None
    try:
        return DET.fromstring(data, forbid_dtd=True)
    except (DET.ParseError, DefusedXmlException, ValueError):
        raise IngestError("unreadable_file",
                          "This .docx file could not be read. Open it in "
                          "Word, save it again as .docx, and upload that.") \
            from None


def load_docx(filename: str, data: bytes) -> Document:
    zf, members = open_zip(data, ".docx")
    if "word/document.xml" not in members:
        raise IngestError("unreadable_file",
                          "This file is not a Word .docx document. Save it "
                          "from Word as .docx and upload it again.")
    styles = {}
    if "word/styles.xml" in members:
        styles = _styles(_parse(read_member(zf, members["word/styles.xml"],
                                            ".docx")))
    root = _parse(read_member(zf, members["word/document.xml"], ".docx"))
    body = _child(root, "body")
    reader = _Reader(styles)
    try:
        if body is not None:
            reader.block(body, "body")
        return reader.document(filename)
    except RecursionError:
        # Belt and braces behind MAX_DEPTH: no input may crash the service.
        raise IngestError("unreadable_file", TOO_DEEP) from None


def _styles(root) -> dict[str, tuple[str, int | None]]:
    """style id -> (name, outline level or None), outline levels inherited
    through `w:basedOn` as Word does."""
    raw = {}
    for st in root:
        if _local(st.tag) != "style":
            continue
        sid = _attr(st, "styleId")
        if not sid:
            continue
        name_el, ppr = _child(st, "name"), _child(st, "pPr")
        based = _child(st, "basedOn")
        lvl = _child(ppr, "outlineLvl") if ppr is not None else None
        raw[sid] = (_attr(name_el, "val") if name_el is not None else sid,
                    _attr(lvl, "val") if lvl is not None else None,
                    _attr(based, "val") if based is not None else None)
    out = {}
    for sid, (name, _, _) in raw.items():
        cur, level, seen = sid, None, set()
        while cur in raw and cur not in seen and level is None:
            seen.add(cur)
            level, cur = raw[cur][1], raw[cur][2]
        out[sid] = (name or sid, _outline(level))
    return out


def _outline(level) -> int | None:
    # Levels 0-8 are headings in the navigation pane; 9 is body text.
    if level is not None and level.isdigit() and int(level) <= 8:
        return int(level)
    return None


# Real documents nest tables and runs a handful of levels deep. A file
# nested hundreds deep is malformed or hostile: a 17 KB upload with 400
# nested tables used to exhaust Python's recursion limit (P29 bench).
MAX_DEPTH = 100
TOO_DEEP = ("This Word file is nested too deeply to read (tables or links "
            "inside each other hundreds of times). Open and re-save it in "
            "Word, then upload it again.")


def _check_depth(depth: int) -> None:
    if depth > MAX_DEPTH:
        raise IngestError("unreadable_file", TOO_DEEP)


class _Reader:
    def __init__(self, styles):
        self.styles = styles
        self.paras: list[dict] = []
        self.chars = 0
        # (paragraph index, start, end) placeholders; paragraph indexes.
        self.equations: list[tuple[int, int, int]] = []
        self.figures: list[int] = []
        self.tables: list[tuple[int, int]] = []
        # The paragraph being read.
        self.parts: list[str] = []
        self.length = 0
        self.has_figure = False

    # -- blocks -------------------------------------------------------------

    def block(self, el, kind: str, depth: int = 0) -> None:
        _check_depth(depth)
        for c in el:
            ln = _local(c.tag)
            if ln == "p":
                self.paragraph(c, kind)
            elif ln == "tbl":
                first = len(self.paras)
                self.block(c, "table", depth + 1)
                if len(self.paras) > first:
                    self.tables.append((first, len(self.paras) - 1))
            elif ln in _BLOCK_CONTAINERS:
                self.block(c, kind, depth + 1)

    def paragraph(self, p, kind: str) -> None:
        self.parts, self.length, self.has_figure = [], 0, False
        index = len(self.paras)
        self.inline(p, index)
        text = "".join(self.parts)
        name, outline = self.style_of(p)
        style = name
        if (outline is not None and name.lower() != "title"
                and not re.search(r"heading\s*\d", name.lower())):
            # from_word recognises headings, and their level, by name
            style = f"Heading {outline + 1}"
        if self.has_figure:
            self.figures.append(index)
        self.chars += len(text) + 2
        if self.chars > MAX_TEXT_CHARS:
            raise IngestError("payload_too_large",
                              f"This document has more than "
                              f"{MAX_TEXT_CHARS:,} characters. Check one "
                              "chapter at a time.")
        self.paras.append({"text": text, "style": style, "kind": kind})

    def style_of(self, p) -> tuple[str, int | None]:
        ppr = _child(p, "pPr")
        if ppr is None:
            return "", None
        ps, lvl = _child(ppr, "pStyle"), _child(ppr, "outlineLvl")
        sid = _attr(ps, "val") if ps is not None else None
        name, outline = self.styles.get(sid, (sid or "", None))
        if lvl is not None:
            outline = _outline(_attr(lvl, "val"))
        return name, outline

    # -- runs ---------------------------------------------------------------

    def add(self, s: str) -> None:
        self.parts.append(s)
        self.length += len(s)

    def inline(self, el, index: int, depth: int = 0) -> None:
        _check_depth(depth)
        for c in el:
            ln = _local(c.tag)
            if ln in _SKIP:
                continue
            if ln == "t":
                self.add(c.text or "")
            elif ln == "tab":
                self.add("\t")
            elif ln in ("br", "cr"):
                self.add("\n")
            elif ln == "noBreakHyphen":
                self.add("-")
            elif ln in ("drawing", "pict", "object"):
                self.has_figure = True
            elif ln in ("oMath", "oMathPara"):
                self.equations.append((index, self.length,
                                       self.length + len(EQUATION)))
                self.add(EQUATION)
            elif ln == "r" and self.hidden(c):
                continue
            else:
                # r, hyperlink, ins, moveTo, fldSimple, smartTag, sdt,
                # sdtContent, AlternateContent/Choice, ...
                self.inline(c, index, depth + 1)

    @staticmethod
    def hidden(run) -> bool:
        rpr = _child(run, "rPr")
        v = _child(rpr, "vanish") if rpr is not None else None
        return v is not None and (_attr(v, "val") or "1").lower() not in _FALSE

    # -- result -------------------------------------------------------------

    def document(self, filename: str) -> Document:
        doc = Document.from_word(self.paras)
        offs = doc.para_offsets
        masked = list(doc.masked)
        structure: list[StructureItem] = list(doc.structure)   # captions
        for i, a, b in self.equations:
            masked[offs[i] + a:offs[i] + b] = " " * (b - a)
            structure.append(StructureItem("equation", offs[i] + a,
                                           offs[i] + b))
            doc.atoms.append((offs[i] + a, offs[i] + b))
        doc.masked = "".join(masked)

        def span(i: int) -> tuple[int, int]:
            return offs[i], offs[i] + len(self.paras[i]["text"])

        structure += [StructureItem("figure", *span(i)) for i in self.figures]
        structure += [StructureItem("table", span(a)[0], span(b)[1])
                      for a, b in self.tables]
        doc.structure = sorted(structure, key=lambda s: (s.start, s.kind))
        doc.path = filename
        doc.segments = [Segment(filename, 0, len(doc.original), 0)]
        return doc
