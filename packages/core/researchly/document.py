"""Markup-aware document handling.

Core idea (borrowed from LTeX+'s "annotated text" pattern, simplified):
instead of *removing* markup, we *mask* it with spaces. The masked text has
exactly the same length and character positions as the original, so any
character offset found by a rule maps 1:1 back to the source file — no offset
arithmetic, no drift.

Supported kinds: markdown / quarto (.md, .qmd, .rmd), latex (.tex), plain text.

Also performs lightweight IMRaD section detection from headings, so rules can
be section-conditioned (the defining Researchly behaviour: the same sentence
gets different advice in Methods vs Discussion).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Section classification
# ---------------------------------------------------------------------------

_SECTION_PATTERNS: list[tuple[str, str]] = [
    # A reference list is not prose (P31): it is masked, never checked.
    (r"^\W*(references|bibliography|literature cited|works cited|"
     r"reference list|cited literature)\W*$", "references"),
    # Before the others: "C Data Appendix" is an appendix, not Methods (P33).
    (r"appendix|appendices|supplement", "appendix"),
    (r"abstract|summary\b", "abstract"),
    (r"introduction|background", "introduction"),
    (r"method|material|model|data\b|analys[ie]s|estimation|inference|"
     r"statistic|design|setting|participants", "methods"),
    (r"result|finding", "results"),
    (r"limitation", "limitations"),
    (r"discussion", "discussion"),
    (r"conclusion", "conclusion"),
]


# Sections that are "no section": no headings at all, before the first
# heading, or under a topical heading the patterns do not know.
_UNHEADED = frozenset({"unknown", "front", "other"})


def classify_heading(text: str) -> str:
    low = text.lower()
    for pat, name in _SECTION_PATTERNS:
        if re.search(pat, low):
            return name
    return "other"


# Depth of each LaTeX sectioning command (smaller = higher up).
TEX_LEVELS = {"part": -1, "chapter": 0, "section": 1, "subsection": 2,
              "subsubsection": 3, "paragraph": 4, "subparagraph": 5}

# Words a heading may consist of and still be a plain section name
# ("Materials and methods", "3.2 Statistical analysis") rather than a
# topical title ("A model of measles transmission").
_SECTION_NAME_WORDS = frozenset("""
    abstract summary introduction background literature review aims aim
    objectives methods method methodology materials material data
    statistical statistics analysis analyses experimental procedures
    results result findings discussion general conclusion conclusions
    concluding remarks limitations strengths appendix appendices
    supplementary supplemental information references bibliography
""".split())
_SECTION_NAME_FILLER = frozenset({"and", "of", "the", "a", "an", "s"})
_NUMBERING = re.compile(
    r"^\s*(?:(?:chapter|part|section|appendix)\s+)?"
    r"(?:[0-9]+|[ivxlc]+|[a-z])(?:[.:][0-9]+)*[.:)]?\s+", re.IGNORECASE)


def is_section_name(title: str) -> bool:
    """True for a heading that is just a section name, numbered or not."""
    words = re.findall(r"[a-z]+", _NUMBERING.sub("", title.lower()))
    words = [w for w in words if w not in _SECTION_NAME_FILLER]
    return bool(words) and all(w in _SECTION_NAME_WORDS for w in words)


def resolve_sections(headings: list["Heading"]) -> None:
    """Give nested headings their parent's section (P28).

    A subsection with no section word ("Priors", "Solver") used to reset
    the section to "other", and one with a stray keyword ("Model fit" under
    Results) used to switch to Methods. Now a heading inherits when it has
    no section word of its own, or when its parent is a plain section name
    ("Results"). A nested heading that is itself a plain section name
    ("Limitations" under Discussion) keeps its own, and so does any nested
    heading under a topical title ("A model of measles transmission").
    Headings without a level (plain text, the abstract environment, a Word
    Title) stand alone and end every open section, as before.
    """
    stack: list[tuple["Heading", bool]] = []     # (heading, authoritative)
    for h in sorted(headings, key=lambda h: h.start):
        if not h.keyword:
            h.keyword = h.section
        own, named = h.keyword, is_section_name(h.text)
        if h.level is None:
            stack = []
            h.section = own
            continue
        while stack and stack[-1][0].level >= h.level:
            stack.pop()
        parent, authority = stack[-1] if stack else (None, False)
        if parent is None or parent.section == "other":
            h.section, auth = own, named
        elif own == "other":
            h.section, auth = parent.section, authority
        elif authority and not named:
            h.section, auth = parent.section, True
        else:
            h.section, auth = own, named
        stack.append((h, auth))


def _mask_references(chars: list[str], headings: list["Heading"]) -> None:
    """Blank every reference-list section: author names, journal
    abbreviations and "et al" are not the author's prose. A Word reference
    list (Zotero, EndNote) is ordinary paragraphs; LaTeX's is already
    masked by \\bibliography and thebibliography."""
    ordered = sorted(headings, key=lambda h: h.start)
    for i, h in enumerate(ordered):
        if h.section != "references":
            continue
        end = next((g.start for g in ordered[i + 1:]
                    if g.section != "references"), len(chars))
        _mask_spans(chars, [(h.start, end)])


@dataclass
class Heading:
    start: int
    text: str
    section: str
    # Where the heading's own text ends. None means "end of its line", which
    # is right for Markdown and Word; a LaTeX `\paragraph{Title.} Text...`
    # shares its line with prose that must not be masked with it.
    end: int | None = None
    # Depth when the markup says (1 = `#`/Heading 1/\section, 0 = \chapter);
    # None for plain text, where headings are guessed and stand alone.
    level: int | None = None
    # The heading's own classification; `section` is the effective one
    # after resolve_sections().
    keyword: str = ""


@dataclass
class Segment:
    """`Document.original[start:end]` came from `path` at `source_start`
    (docs/s2-design.md §4). A single-file document has one segment."""
    path: str
    start: int
    end: int
    source_start: int = 0


# A caption typed in a body style: "Table 2: ...", "Figure 3. ...".
_TYPED_CAPTION = re.compile(
    r"(?:Fig(?:ure)?\.?|Table)\s+(?:[A-Z]\.?)?\d+(?:\.\d+)*[a-z]?\s*[:.|]\s+\S")


# A list-of-figures or contents entry: dot leaders or a page number at the
# end ("Figure 1: Study area ..... 12"). Not a caption.
_TOC_ENTRY = re.compile(r"(?:\.{3,}|\u2026|\t)\s*\d+\s*$|\s{2,}\d+\s*$")


def _typed_caption(text: str, style: str) -> bool:
    if style.startswith(("toc", "tableoffigures")):
        return False
    return bool(_TYPED_CAPTION.match(text)) and not _TOC_ENTRY.search(text)


@dataclass
class StructureItem:
    """A figure, table, equation, caption or citation (kept for S2b)."""
    kind: str            # figure | table | equation | caption | citation |
    #                      ref | label (S2b cross-references) |
    #                      styled_body (a heading style on body text, P33)
    start: int
    end: int
    label: str | None = None


@dataclass
class Document:
    original: str
    masked: str
    kind: str
    headings: list[Heading] = field(default_factory=list)
    path: str = "<text>"
    # For documents built from Word paragraphs: char offset where each
    # paragraph starts in `original`, so suggestions can be mapped back to
    # (paragraph index, in-paragraph position) for Office JS.
    para_offsets: list[int] = field(default_factory=list)
    # (start, end) spans that are table cells, not prose. Metrics exclude
    # them: a table of parameter values is not a set of long sentences.
    table_spans: list[tuple[int, int]] = field(default_factory=list)
    # Set by the file adapters (researchly.ingest); empty for pasted text.
    segments: list[Segment] = field(default_factory=list)
    structure: list[StructureItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Masked spans that stood for a word in the sentence: maths, citations,
    # cross-references, code, URLs, Word equations. Formatting (\emph{,
    # **, a heading) is masked too but stands for nothing, so it is not here.
    atoms: list[tuple[int, int]] = field(default_factory=list)
    # The article-type profile's section for prose with no IMRaD heading
    # over it (S4): a commentary's body is argued like a Discussion, a
    # pasted abstract is an abstract. None keeps "unknown"/"front"/"other".
    default_section: Optional[str] = None
    _line_starts: list[int] = field(default_factory=list, repr=False)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_path(cls, path: str | Path) -> "Document":
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix in {".docx", ".zip"}:
            # Binary containers go through the file adapters, so the CLI
            # reads them exactly as the hosted engine does.
            from .ingest import load_bytes
            doc = load_bytes(path.name, path.read_bytes())
            doc.path = str(path)
            return doc
        text = path.read_text(encoding="utf-8")
        if suffix in {".md", ".qmd", ".rmd", ".markdown"}:
            kind = "markdown"
        elif suffix in {".tex", ".ltx"}:
            kind = "latex"
        else:
            kind = "plain"
        doc = cls.from_text(text, kind)
        doc.path = str(path)
        return doc

    @classmethod
    def from_text(cls, text: str, kind: str = "plain", *,
                  locate=None, mask_references: bool = True) -> "Document":
        """`locate(offset) -> str` words a position in a warning; the
        Overleaf adapter passes one that names the source file.
        `from_word` masks reference lists itself, once it knows which
        "headings" were really table cells."""
        structure: list[StructureItem] = []
        warnings: list[str] = []
        if kind == "markdown":
            masked, headings = _mask_markdown(text)
        elif kind == "latex":
            # Parsed with pylatexenc; falls back to `_mask_latex` (with a
            # warning) when the source cannot be parsed. Imported here
            # because the ingest package imports this module.
            from .ingest.latex import mask_latex
            res = mask_latex(text, locate)
            masked, headings = res.masked, res.headings
            structure, warnings = res.structure, res.warnings
        else:
            masked, headings = text, _detect_plain_headings(text)
        atoms = (res.atoms if kind == "latex"
                 else inline_atoms(text, kind) if kind == "markdown" else [])
        if kind == "plain":
            layout = layout_spans(text) + url_spans(text)
            if layout:
                masked = list(masked)
                _mask_spans(masked, layout)
                masked = "".join(masked)
                atoms = sorted(atoms + layout)
        # Mask heading TEXT as well (after recording it): headings are not
        # sentences, and without terminal punctuation the parser merges them
        # into the following paragraph's first sentence, corrupting
        # subject/verb analysis ("Results Selected variables are shown...").
        chars = list(masked)
        for h in headings:
            end = h.end if h.end is not None else masked.find("\n", h.start)
            end = end if end != -1 else len(masked)
            _mask_spans(chars, [(h.start, end)])
        resolve_sections(headings)
        if mask_references:
            _mask_references(chars, headings)
        masked = "".join(chars)
        doc = cls(original=text, masked=masked, kind=kind, headings=headings,
                  structure=structure, warnings=warnings, atoms=atoms)
        doc._line_starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
        return doc

    @classmethod
    def from_word(cls, paragraphs: list[dict]) -> "Document":
        """Build a Document from Office JS Word paragraphs.

        Each item: {"text": str, "style": str, "kind": str} — style is the
        Word paragraph style (e.g. "Heading1", "Heading 2", "Title",
        "Normal"). Word headings are detected from STYLE (far more reliable
        than keywords), classified into IMRaD sections, and masked like all
        other headings. Falls back to plain-text keyword heading detection
        for authors who type headings without applying a style.

        `kind` is "body" (default) or "table". Table cells arrive through
        the same paragraph collection as prose; counted as prose they skewed
        sentence-length and passive-voice metrics, and a cell reading
        "Methods" could re-section the rest of the document. They are
        recorded in `table_spans` so metrics can exclude them.
        """
        texts = [p.get("text") or "" for p in paragraphs]
        combined = "\n\n".join(texts)
        doc = cls.from_text(combined, kind="plain", mask_references=False)

        offsets: list[int] = []
        pos = 0
        for t in texts:
            offsets.append(pos)
            pos += len(t) + 2
        doc.para_offsets = offsets

        chars = list(doc.masked)
        style_headings: list[Heading] = []
        table_spans: list[tuple[int, int]] = []
        captions: list[StructureItem] = []
        for i, p in enumerate(paragraphs):
            style = (p.get("style") or "").lower().replace(" ", "")
            title = texts[i].strip()
            if p.get("kind") == "table" and title:
                table_spans.append((offsets[i], offsets[i] + len(texts[i])))
                continue          # never a heading, never prose
            if not title:
                continue
            if "caption" in style:
                # Recorded here, not in the .docx reader, so the Word
                # add-in's paragraphs and an uploaded file agree (S2b).
                captions.append(StructureItem(
                    "caption", offsets[i], offsets[i] + len(texts[i])))
                continue
            if _typed_caption(title, style):
                # A caption typed in a body style ("Table 2: ...", common
                # after a PDF conversion) is still a caption (P33), but a
                # weaker signal than Word's caption style: marked "typed".
                captions.append(StructureItem(
                    "caption", offsets[i], offsets[i] + len(texts[i]),
                    label="typed"))
                continue
            for line in re.finditer(r"\n[ \t]*([^\n]+)", texts[i]):
                # A caption a PDF converter left inside a paragraph, on a
                # line of its own.
                if _typed_caption(line.group(1), style):
                    captions.append(StructureItem(
                        "caption", offsets[i] + line.start(1),
                        offsets[i] + line.end(1), label="typed"))
            if "heading" in style or style == "title":
                lvl = re.search(r"heading(\d)", style)
                level = int(lvl.group(1)) if lvl else None
                start, end = offsets[i], offsets[i] + len(texts[i])
                if len(title.split()) > (RUN_IN_WORDS if lvl else 40):
                    # Body text in a heading style: check it as prose, and
                    # keep the heading only if one can be split off (P33).
                    lead = len(texts[i]) - len(texts[i].lstrip())
                    cut = split_run_in(title)
                    captions.append(StructureItem(
                        "styled_body", start, end,
                        label=None if cut is None else "run-in"))
                    if cut is None:
                        continue
                    end = start + lead + cut
                    title = texts[i][lead:lead + cut].strip()
                # A Title-styled paragraph is the document's title, not a
                # section: "A compartmental model of..." is not Methods.
                style_headings.append(
                    Heading(start, title,
                            "front" if style == "title" else classify_heading(title),
                            end=end, level=level))
                _mask_spans(chars, [(start, end)])
        doc.table_spans = table_spans
        doc.structure = captions
        if table_spans:
            # from_text() already ran keyword heading detection over the
            # combined string, before table cells were known. A cell reading
            # "Methods" would otherwise re-section everything after it.
            doc.headings = [h for h in doc.headings
                            if not doc.in_table(h.start)]

        if style_headings:
            # A document that uses heading styles uses them for its
            # headings: a line that merely reads like one ("Fit statistics"
            # in a table, "Data" in a figure) is not one (P33).
            doc.headings = sorted(style_headings, key=lambda h: h.start)
            resolve_sections(doc.headings)
        _mask_references(chars, doc.headings)
        doc.masked = "".join(chars)
        doc.kind = "word"
        return doc

    def in_table(self, offset: int) -> bool:
        """Is this offset inside a Word table cell?"""
        return any(a <= offset < b for a, b in self.table_spans)

    def locate(self, offset: int) -> tuple[int, int]:
        """(paragraph index, in-paragraph offset) for a char offset."""
        if not self.para_offsets:
            return 0, offset
        idx = bisect_right(self.para_offsets, offset) - 1
        return idx, offset - self.para_offsets[idx]

    # -- position helpers ---------------------------------------------------

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based (line, col) for a character offset in the original text."""
        line_idx = bisect_right(self._line_starts, offset) - 1
        return line_idx + 1, offset - self._line_starts[line_idx] + 1

    def masked_content(self, start: int, end: int) -> bool:
        """True if [start, end) overlaps an atom: masked material that stood
        for a word in the sentence (maths, a citation, code). Masked
        formatting such as `\\emph{` or `**` does not count: "an
        \\emph{large} rise" is still "an large rise" to the reader."""
        return any(a < end and start < b for a, b in self.atoms)

    def touches_masked(self, start: int, end: int) -> bool:
        """True if masked material lies inside [start, end) or in the spaces
        either side of it (across a wrapped line, not a paragraph break).

        Masking blanks inline maths, citations and code to spaces, so the
        words around them look adjacent: "and $C(0)$ and" reads as a doubled
        "and and", "An $\\exp(1)$ prior" as "An prior". A finding whose
        evidence crosses a blank is about the masking, not the writing.
        """
        m = self.masked
        a = self._blank_run(start, -1)
        b = self._blank_run(end, +1)
        return self.masked_content(a, b)

    def _blank_run(self, i: int, step: int) -> int:
        """Walk from i over blanks in the masked text, crossing at most one
        line break (a sentence wrapped in the source) but never a blank line
        (a paragraph break)."""
        m, newlines = self.masked, 0
        while True:
            j = i if step > 0 else i - 1
            if j < 0 or j >= len(m) or m[j] not in " \t\n":
                return i
            if m[j] == "\n":
                newlines += 1
                if newlines > 1:
                    return i
            i += step

    def section_at(self, offset: int) -> str:
        """IMRaD section governing this offset ('unknown' if no headings;
        the profile's `default_section`, if set, for unheaded prose)."""
        current = "unknown"
        if self.headings:
            current = "front"
            for h in self.headings:
                if h.start > offset:
                    break
                current = h.section
        if self.default_section and current in _UNHEADED:
            return self.default_section
        return current


# ---------------------------------------------------------------------------
# Masking machinery
# ---------------------------------------------------------------------------

def _mask_spans(chars: list[str], spans: list[tuple[int, int]]) -> None:
    """Overwrite [start, end) spans with spaces, preserving newlines."""
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "


def _find_all(pattern: str, text: str, flags: int = 0) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(pattern, text, flags)]


# -- Markdown / Quarto ------------------------------------------------------

def _mask_markdown(text: str) -> tuple[str, list[Heading]]:
    chars = list(text)
    spans: list[tuple[int, int]] = []

    # YAML front matter at very top
    m = re.match(r"\A---\n.*?\n(---|\.\.\.)\s*\n", text, re.DOTALL)
    if m:
        spans.append((0, m.end()))

    # Fenced code blocks (``` or ~~~), including Quarto chunks
    spans += _find_all(r"^(```|~~~).*?^\1[^\n]*$", text, re.DOTALL | re.MULTILINE)
    # Inline code
    spans += _find_all(r"`[^`\n]+`", text)
    # Display + inline math
    spans += _find_all(r"\$\$.*?\$\$", text, re.DOTALL)
    spans += _find_all(r"(?<![\\$])\$[^$\n]+\$", text)
    # Bracketed citation groups [ ... @key ... ] and bare @citekeys
    spans += _find_all(r"\[[^\]\n]*@[^\]\n]*\]", text)
    spans += _find_all(r"(?<![\w.])@[\w:.\-]+", text)
    # Images entirely; links keep their text
    spans += _find_all(r"!\[[^\]]*\]\([^)]*\)", text)
    for m2 in re.finditer(r"\[([^\]\n]+)\]\(([^)]*)\)", text):
        spans.append((m2.start(), m2.start(1)))          # '['
        spans.append((m2.end(1), m2.end()))              # '](url)'
    # HTML tags and comments
    spans += _find_all(r"<!--.*?-->", text, re.DOTALL)
    spans += _find_all(r"</?[a-zA-Z][^>\n]*>", text)
    # Cross-reference / div fences (Quarto ::: blocks) — markers only
    spans += _find_all(r"^:{3,}.*$", text, re.MULTILINE)
    # Emphasis markers (keep the emphasised words)
    spans += _find_all(r"\*{1,3}", text)
    spans += _find_all(r"(?<![\w])_{1,3}(?=\w)|(?<=\w)_{1,3}(?![\w])", text)

    _mask_spans(chars, spans)

    # Headings: record, then mask the leading hashes (keep the text so spaCy
    # still sees it, but rules can skip heading lines via section metadata).
    headings: list[Heading] = []
    masked_so_far = "".join(chars)
    for m3 in re.finditer(r"^(#{1,6})[ \t]+([^\n{]+)", masked_so_far, re.MULTILINE):
        title = m3.group(2).strip()
        if title:
            headings.append(Heading(m3.start(), title, classify_heading(title),
                                    level=len(m3.group(1))))
        _mask_spans(chars, [(m3.start(1), m3.end(1))])

    return "".join(chars), headings


# -- LaTeX ------------------------------------------------------------------

_TEX_MASK_ENVS = (
    "equation", "align", "alignat", "gather", "eqnarray", "multline",
    "displaymath", "math", "verbatim", "lstlisting", "minted", "tikzpicture",
    "tabular", "array",
    # P29 real documents: pandoc/knitr code blocks, pseudo-code
    "Shaded", "Highlighting", "Verbatim", "algorithmic", "algorithmicx",
    "algorithm", "comment",
)
_TEX_KEEP_CONTENT = (
    "emph", "textbf", "textit", "textsc", "underline", "mbox",
    "caption", "title", "textnormal", "textrm",
)
_TEX_MASK_WHOLE = (
    "cite", "citep", "citet", "citealt", "citealp", "parencite", "textcite",
    "ref", "eqref", "autoref", "cref", "Cref", "vref", "label", "url",
    "includegraphics", "input", "include", "bibliography", "bibliographystyle",
    "usepackage", "documentclass", "footnote", "footnotemark", "href",
    # code is not prose (P28 for the parser; P29 for this fallback)
    "texttt", "code", "path", "verb",
    # definitions, not text (P29: "\\newacronym{MTHM}{MTHM}" read as a
    # doubled word)
    "newacronym", "newglossaryentry", "newtheorem", "theoremstyle",
    "newcommand", "renewcommand", "providecommand", "DeclareMathOperator",
)


# Inline material per markup: what stands for a word in the sentence.
_ATOM_PATTERNS = {
    "markdown": (r"`[^`\n]+`", r"\$\$.*?\$\$", r"(?<![\\$])\$[^$\n]+\$",
                 r"\[[^\]\n]*@[^\]\n]*\]", r"(?<![\w.])@[\w:.\-]+",
                 r"!\[[^\]]*\]\([^)]*\)"),
    "latex": (r"\$\$.*?\$\$", r"(?<!\\)\$[^$]+\$", r"\\\[.*?\\\]",
              r"\\\(.*?\\\)",
              r"\\(?:[a-zA-Z]*cite[a-zA-Z]*|ref|eqref|autoref|[cC]ref|url|"
              r"texttt|verb)\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})+"),
}


def inline_atoms(text: str, kind: str) -> list[tuple[int, int]]:
    """Atoms (see Document.atoms) found by pattern, for the regex maskers."""
    spans: list[tuple[int, int]] = []
    for pat in _ATOM_PATTERNS.get(kind, ()):
        spans += _find_all(pat, text, re.DOTALL)
    return sorted(spans)


def _mask_latex(text: str) -> tuple[str, list[Heading]]:
    chars = list(text)
    spans: list[tuple[int, int]] = []

    # Comments (unescaped % to end of line)
    spans += _find_all(r"(?<!\\)%[^\n]*", text)
    # Whole environments that are not prose
    env_alt = "|".join(_TEX_MASK_ENVS)
    spans += _find_all(
        rf"\\begin\{{({env_alt})\*?\}}.*?\\end\{{\1\*?\}}", text, re.DOTALL)
    # Math
    spans += _find_all(r"\$\$.*?\$\$", text, re.DOTALL)
    spans += _find_all(r"(?<!\\)\$[^$]+\$", text, re.DOTALL)
    spans += _find_all(r"\\\[.*?\\\]", text, re.DOTALL)
    spans += _find_all(r"\\\(.*?\\\)", text, re.DOTALL)
    # Commands whose whole call should vanish (incl. optional args)
    whole_alt = "|".join(_TEX_MASK_WHOLE)
    spans += _find_all(
        rf"\\({whole_alt})\*?(\[[^\]]*\])*(\{{[^{{}}]*\}})+", text)

    # Sectioning: record heading, keep title text, mask the command wrapper
    headings: list[Heading] = []
    for m in re.finditer(
            r"\\(part|chapter|section|subsection|subsubsection|paragraph|"
            r"subparagraph)\*?"
            r"\{([^{}]+)\}", text):
        title = m.group(2).strip()
        headings.append(Heading(m.start(), title, classify_heading(title),
                                level=TEX_LEVELS[m.group(1)]))
        spans.append((m.start(), m.start(2)))
        spans.append((m.end(2), m.end()))

    # Commands that keep their content: mask "\cmd{" and the matching "}"
    keep_alt = "|".join(_TEX_KEEP_CONTENT)
    for m in re.finditer(rf"\\({keep_alt})\*?\{{([^{{}}]*)\}}", text):
        spans.append((m.start(), m.start(2)))
        spans.append((m.end(2), m.end()))

    # \begin{...} / \end{...} of prose environments (abstract, document, ...)
    spans += _find_all(r"\\(begin|end)\{[^{}]*\}(\[[^\]]*\])?", text)
    # Any remaining bare command (\item, \noindent, \alpha, \\ ...)
    spans += _find_all(r"\\[a-zA-Z@]+\*?", text)
    spans += _find_all(r"\\[\\,;:!]", text)
    # Leftover braces and tex-special characters
    spans += _find_all(r"[{}~^]", text)

    _mask_spans(chars, spans)

    # LaTeX abstract environment counts as a section
    m_abs = re.search(r"\\begin\{abstract\}", text)
    if m_abs:
        headings.append(Heading(m_abs.start(), "Abstract", "abstract"))
        headings.sort(key=lambda h: h.start)

    return "".join(chars), headings


# -- Plain text -------------------------------------------------------------

# -- Text that came out of a PDF ---------------------------------------------
#
# A PDF converted to Word or pasted as text (P33) keeps the PDF's layout:
# table rows as columns aligned with spaces, displayed equations as runs of
# symbols and one-letter variables ("d log π j t = (1 − ε)d log mc j t").
# Checked as prose they produced doubled-word, grammar and long-sentence
# findings about the conversion, not the writing. Plain text and Word only:
# LaTeX and Markdown mark their tables and maths.

# Two columns: a gap of four or more spaces inside a line.
_COLUMN_GAP = re.compile(r"\S {4,}\S")
_MATH_CHAR = re.compile(
    "[Ͱ-Ͽ∀-⋿←-⇿′-‷̀-ͯ"
    "=<>+^|¡¢£¤∞]")
_RELATION = re.compile("[=<>≤≥≈≡∈∼∝]")
_TOKEN_PUNCT = ".,;:()[]{}\"'’“”"


def _math_token(tok: str) -> bool | None:
    """True for a token of flattened maths, False for a word, None for
    punctuation or a bare number (neither)."""
    core = tok.strip(_TOKEN_PUNCT)
    if not core or re.fullmatch(r"[\d.,%-]+", core):
        return None
    if _MATH_CHAR.search(core):
        return True
    return len(core) == 1 and core.isalpha() and core not in "aAI"


def layout_spans(text: str) -> list[tuple[int, int]]:
    """Lines of a PDF's layout rather than its prose: aligned columns, and
    displayed equations flattened to text. Masked and kept as atoms."""
    spans = []
    for m in re.finditer(r"[^\n]+", text):
        line = m.group()
        if _COLUMN_GAP.search(line.strip()):
            spans.append((m.start(), m.end()))
            continue
        if not _RELATION.search(line):
            continue
        kinds = [k for k in map(_math_token, line.split()) if k is not None]
        if len(kinds) >= 3 and sum(kinds) >= 0.5 * len(kinds):
            spans.append((m.start(), m.end()))
    return spans


_URL = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def url_spans(text: str) -> list[tuple[int, int]]:
    """Web and e-mail addresses in plain text: not words to check."""
    out = []
    for m in _URL.finditer(text):
        end = m.end()
        while end > m.start() and text[end - 1] in ".,;:)]'\"":
            end -= 1
        out.append((m.start(), end))
    return out


# A heading-styled paragraph longer than this is body text carrying a
# heading style: a PDF conversion, or a heading typed run-in ("1
# Introduction How will ..."). Masked whole, it hid the Introduction (P33).
RUN_IN_WORDS = 25
_MINOR_WORDS = frozenset(
    "a an and as at but by for from in into of on or the to vs via with"
    .split())


def split_run_in(title: str) -> int | None:
    """Where the body starts in a run-in heading paragraph, else None.

    "2 Methods We fitted a model ..." -> the offset of "We": the capitalised
    word just before the first lower-case content word. The heading must be
    numbered ("2", "3.1", "A") and keep at least one word of its own, so a
    sentence wearing a heading style ("Appendix Figure B.1 compares ...")
    is not split at all.
    """
    num = _NUMBERING.match(title)
    if not num:
        return None
    words = [w for w in re.finditer(r"\S+", title) if w.start() >= num.end()]
    for i, w in enumerate(words):
        tok = w.group().strip(_TOKEN_PUNCT)
        if not tok or not tok[0].islower() or tok in _MINOR_WORDS:
            continue
        j = i - 1
        while j >= 0 and not words[j].group()[0].isupper():
            j -= 1
        if j < 1 or j > 15:
            return None
        return words[j].start()
    return None


def _detect_plain_headings(text: str) -> list[Heading]:
    """Short lines that look like section titles (no trailing period)."""
    headings = []
    for m in re.finditer(r"^([A-Z][A-Za-z &\-]{2,60})\s*$", text, re.MULTILINE):
        title = m.group(1).strip()
        if "   " in title:                  # aligned columns: a table row
            continue
        section = classify_heading(title)
        if section != "other":
            headings.append(Heading(m.start(), title, section))
    return headings
