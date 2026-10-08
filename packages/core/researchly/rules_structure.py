"""Structural checks: figures, tables, equations and the text citing them
(S2b; owner decision P4).

They read `researchly.structure`, which only LaTeX and Word documents have:
pasted plain text gets none of these checks rather than a guess. Messages
ask a question; the author knows whether the figure is meant to be cited.
"""

from __future__ import annotations

import re

from .document import _RELATION, Document
from .engine import Category, Suggestion, rule
from .structure import Structure, analyse, number_text

# "Figure 3 of Smith et al." / "Table 2 in [12]": another paper's float.
_ELSEWHERE = re.compile(
    r"\s*(?:of|in|from)\s+(?:ref\b|refs?\.|\[|\(|[A-Z][A-Za-z'-]+\s+et\s+al)")


_CAPTION_WORD = {"figure": r"Fig(?:ure)?\.?", "table": "Table"}


def structure_of(document: Document) -> Structure:
    """Analysed once per document and shared by every structural rule."""
    st = getattr(document, "_structure", None)
    if st is None:
        st = analyse(document)
        document._structure = st
    return st


def _anchor(document: Document, start: int, end: int,
            limit: int = 80) -> tuple[int, int]:
    """A short span to highlight: the opening words of a caption."""
    stop = min(end, start + limit)
    text = document.original
    dot = text.find(". ", start, stop)
    return start, (dot + 1 if dot > start + 8 else stop)


def _word_near(document: Document, start: int, end: int) -> tuple[int, int]:
    """A \\ref is masked markup and is never highlighted: point at the word
    before it ("Figure~\\ref{x}" -> "Figure"), else the word after."""
    m = document.masked
    if m[start:end].strip():
        return start, end
    before = re.search(r"([A-Za-z][\w.-]*)[^\w\n]*\n?[^\w\n]*$",
                       m[max(0, start - 40):start])
    if before:
        a = max(0, start - 40) + before.start(1)
        return a, a + len(before.group(1))
    after = re.match(r"\W*?([A-Za-z][\w-]*)", m[end:end + 40])
    if after:
        return end + after.start(1), end + after.end(1)
    return start, end


def _text_mentions(st: Structure):
    """Mentions in running text (not captions), resolved to their float."""
    for m in st.mentions:
        if m.in_caption or m.supplementary:
            continue
        if m.label is not None:
            f = st.float_for(m)
            if f is not None:
                yield m, [f]
            continue
        found = [f for f in st.floats
                 if f.kind == m.kind and f.number in m.numbers]
        if found:
            yield m, found


# --- X101–X104: are figures and tables cited, in order, and do the
# --- citations point at something? ------------------------------------------

@rule("X101", "float-not-cited", Category.CONVENTION,
      "A figure or table the text never cites.",
      'Every figure and table should be cited in the text, so the reader '
      'knows when to look at it and what to see there. One that is never '
      'cited is either missing its sentence in the Results or not needed.',
      plain=('The text never mentions this figure or table. Readers need a '
             'sentence that tells them when to look at it and what to see. If no '
             'sentence needs it, it may not be needed.'),
      source="ICMJE",
      scope="document")
def x101_float_not_cited(doc, document: Document):
    st = structure_of(document)
    cited = {id(f) for _, fs in _text_mentions(st) for f in fs}
    # Cited from another float's caption ("as in Table 2") still sends the
    # reader to it; only a float's own caption does not count.
    for m in st.mentions:
        if m.in_caption and not m.supplementary:
            for f in ([st.float_for(m)] if m.label is not None else
                      [f for f in st.floats
                       if f.kind == m.kind and f.number in m.numbers]):
                if f is not None and f.caption is not None and not (
                        f.caption.start <= m.start < f.caption.end):
                    cited.add(id(f))
    for f in st.floats:
        if f.number is None or f.caption is None or id(f) in cited:
            continue
        a, b = _anchor(document, f.caption.start, f.caption.end)
        yield Suggestion(
            message=f"{f.name} is never cited in the text — where should "
                    "the reader look at it?",
            start=a, end=b)


@rule("X102", "float-cited-out-of-order", Category.CONVENTION,
      "Figures or tables first cited out of numerical order.",
      'Figures and tables are numbered in the order the text first cites '
      'them, so a reader meets Figure 2 before Figure 3. When the text '
      'cites Figure 3 first, either the numbering or the order of the '
      'argument needs changing.',
      plain=('Figures and tables should be numbered in the order you first '
             'mention them. Here a later one is mentioned before an earlier one. '
             'Renumber them, or change the order of the text.'),
      source="ICMJE",
      scope="document")
def x102_cited_out_of_order(doc, document: Document):
    st = structure_of(document)
    seen: set = set()
    highest: dict = {}                      # (kind, chapter) -> number
    for m, fs in _text_mentions(st):
        new = [f for f in fs if id(f) not in seen and not f.appendix]
        for f in sorted(new, key=lambda f: f.number):
            seen.add(id(f))
            group = (f.kind, f.number[:-1])      # per chapter in a thesis
            top = highest.get(group)
            if top is not None and f.number < top[0]:
                a, b = _word_near(document, m.start, m.end)
                yield Suggestion(
                    message=f"{f.name} is first cited after {top[1]} — "
                            "renumber, or cite them in order?",
                    start=a, end=b)
            elif top is None or f.number > top[0]:
                highest[group] = (f.number, f.name)


@rule("X103", "broken-cross-reference", Category.CORRECTION,
      "A cross-reference to a figure, table or label that does not exist.",
      "A \\ref to a label that is never defined prints as '??' in the PDF; "
      "a 'Figure 5' in a document with four figures sends the reader "
      'nowhere. Usually a typo in the label or a figure that was removed.',
      plain=('The text refers to a figure, table or label that does not exist. '
             "In LaTeX this prints as '??'. It is usually a typo in the label, "
             'or a figure that was removed.'),
      source="ICMJE",
      scope="document")
def x103_broken_reference(doc, document: Document):
    st = structure_of(document)
    numbered = {k: {f.number for f in st.floats
                    if f.kind == k and f.number is not None}
                for k in ("figure", "table")}
    for m in st.mentions:
        if m.supplementary:
            continue
        if m.label is not None:
            if st.resolve(m.label) is None:
                a, b = _word_near(document, m.start, m.end)
                yield Suggestion(
                    message=f"'{m.label}' is not defined anywhere — a typo "
                            "in the label, or a removed figure? It prints "
                            "as '??'.",
                    start=a, end=b)
            continue
        have = numbered.get(m.kind) or set()
        if not have or m.in_caption:
            continue                    # the document has none to check
        if _ELSEWHERE.match(document.masked, m.end):
            continue
        # A thesis chapter cites figures of other chapters: only judge
        # numbers whose chapter is in this document.
        chapters = {n[:-1] for n in have}
        missing = [n for n in m.numbers
                   if n not in have and n[:-1] in chapters]
        # A caption a converter ran into a paragraph ("... linear. Figure
        # C.2: Scatterplot of ...") was not found as a float, but the
        # figure is there (P33).
        missing = [n for n in missing if not re.search(
            rf"\b{_CAPTION_WORD[m.kind]}\s+{re.escape(number_text(n))}"
            r"\s*:\s*\S", document.original)]
        if missing:
            name = number_text(missing[0])
            yield Suggestion(
                message=f"There is no {m.kind.capitalize()} {name} in this "
                        "document — renumbered, or removed?",
                start=m.start, end=m.end)


@rule("X104", "float-before-first-citation", Category.CONVENTION,
      "A figure or table placed before the text first cites it.",
      'A reader should meet the sentence that cites a figure before the '
      'figure itself; placed earlier, it interrupts the paragraph before '
      'it with something not yet introduced. Word documents only: LaTeX '
      'places floats itself.',
      plain=('This figure or table appears before the sentence that first '
             'mentions it. Move it after that paragraph, so readers meet the '
             'explanation before the picture.'),
      source="ICMJE",
      scope="document")
def x104_before_first_citation(doc, document: Document):
    if document.kind != "word":
        return
    st = structure_of(document)
    first: dict = {}
    for m, fs in _text_mentions(st):
        for f in fs:
            first.setdefault(id(f), m)
    for f in st.floats:
        m = first.get(id(f))
        # Only a caption made with Word's caption style: a typed one is a
        # guess, and in a supplement every table precedes its sentence
        # (33 such flags on PMC supplements, P33).
        if (m is not None and f.caption is not None and not f.appendix
                and f.caption.label != "typed" and m.start > f.end):
            a, b = _anchor(document, f.caption.start, f.caption.end)
            yield Suggestion(
                message=f"{f.name} comes before the text first cites it — "
                        "move it after that paragraph?",
                start=a, end=b)


# --- X202: can the caption be read on its own? -----------------------------------------

def _caption_body(document: Document, cap) -> tuple[int, str]:
    """Where a caption's own words start, and the words: without
    `\\caption{` (masked) or a Word caption's "Figure 2." prefix."""
    m = document.masked
    a = cap.start
    while a < cap.end and m[a].isspace():
        a += 1
    prefix = _WORD_PREFIX.match(m, a, cap.end)
    if prefix:
        a = prefix.end()
    return a, m[a:cap.end]


_WORD_PREFIX = re.compile(
    r"(?:Fig(?:ure)?\.?|Table)\s*[SA]?\d+(?:\.\d+)?[a-z]?\s*[.:|\-–—]?\s*",
    re.IGNORECASE)
_WORDS = re.compile(r"[A-Za-z][A-Za-z'-]*")


@rule("X202", "caption-too-short", Category.IMPROVEMENT,
      "A figure caption too short to be read on its own.",
      'Readers look at figures and tables before they read the text, and '
      "many read nothing else. A caption should state the figure's point "
      'and define what it shows, so the figure can be read unaided; a '
      'label of two or three words cannot.',
      plain=('This figure caption is only a few words. Many readers look at the '
             'figures first, so the caption should say what the figure shows and '
             'what each part means, without needing the main text.'),
      source="§9.7",
      scope="document")
def x202_caption_too_short(doc, document: Document):
    st = structure_of(document)
    for f in st.floats:
        # A table takes a short title (ICMJE: "a short or an abbreviated
        # heading"); only a figure's caption must stand on its own. On 140
        # published articles nearly every X202 was a table title (P33).
        if f.caption is None or f.number is None or f.kind != "figure":
            continue
        a, body = _caption_body(document, f.caption)
        n = len(_WORDS.findall(body))
        if 0 < n < 5:
            yield Suggestion(
                message=f"The caption of {f.name} has {n} word"
                        f"{'s' if n != 1 else ''} — what should the reader "
                        "see in it, and what does each element show?",
                start=a, end=a + len(body.rstrip()))


# --- X301: is every numbered equation referred to? ----------------------------------

_NUMBERED_ENV = re.compile(
    r"\\begin\{(equation|align|alignat|gather|multline|eqnarray|flalign|"
    r"dmath)\}")


@rule("X301", "equation-not-referenced", Category.PREFERENCE,
      "A numbered equation the text never refers to.",
      'Introduce an equation, display it, then interpret it. A numbered '
      'equation the text never refers back to is often one that floats in '
      'unannounced or is never interpreted; if so, remove the number '
      '(equation*).',
      plain=('This equation has a number but the text never refers to it. '
             'Numbers are for equations you refer back to. Either mention it in '
             'the text, or remove the number.'),
      source="§9.2",
      scope="document")
def x301_equation_not_referenced(doc, document: Document):
    if document.kind != "latex":
        return
    st = structure_of(document)
    src = document.original
    referred = {st.resolve(m.label) for m in st.mentions if m.label}
    written = _written_equation_numbers(document.masked)
    chapters = sorted(h.start for h in document.headings if h.level == 0)
    counter: dict = {}
    for it in document.structure:
        if it.kind != "equation":
            continue
        env = _NUMBERED_ENV.match(src, it.start)
        if not env:
            continue
        body = src[it.start:it.end]
        # The numbers LaTeX gives it, to match "Eq. (3)" typed by hand (P33).
        chapter = sum(1 for c in chapters if c < it.start)
        first = counter.get(chapter, 0) + 1
        counter[chapter] = first - 1 + _numbers_in(env.group(1), body)
        mine = {str(k) for k in range(first, counter[chapter] + 1)}
        if chapters:
            mine = {f"{chapter}.{k}" for k in mine} | mine
        if mine & written:
            continue
        labels = {k.strip() for k in re.findall(r"\\label\s*\{([^{}]+)\}",
                                                body)}
        if labels & referred:
            continue
        if not labels and re.search(r"\\(?:nonumber|notag)\b", body):
            continue
        a, b = _word_near(document, it.start, it.start)
        yield Suggestion(
            message="This equation is numbered but the text never refers "
                    "to it — is it introduced and interpreted? If so, it "
                    "can go unnumbered.",
            start=a, end=b)


_EQ_WRITTEN = re.compile(
    r"\b(?:Eqs?\.?|Eqns?\.?|Equations?)\s*~?((?:\(?\s*\d+(?:\.\d+)?[a-z]?\s*\)?"
    r"(?:\s*(?:,|and|&|to|[-\u2013\u2014])\s*)?)+)", re.IGNORECASE)


def _written_equation_numbers(text: str) -> set[str]:
    """Numbers typed after "Eq."/"Equation(s)": "Eqs. (2)-(4)" -> 2, 3, 4."""
    out: set[str] = set()
    for m in _EQ_WRITTEN.finditer(text):
        listing = m.group(1)
        nums = re.findall(r"\d+(?:\.\d+)?", listing)
        out.update(nums)
        for a, b in re.findall(r"(\d+)\)?\s*(?:to|[-\u2013\u2014])\s*\(?(\d+)\b",
                               listing):
            if 0 < int(b) - int(a) < 50:
                out.update(str(k) for k in range(int(a), int(b) + 1))
    return out


def _numbers_in(env: str, body: str) -> int:
    """How many numbers a numbered environment prints (rows of an align,
    less any \\nonumber / \\notag)."""
    if env in ("equation", "multline", "dmath"):
        return 1
    rows = len(re.findall(r"\\\\(?!\s*\\end)", body)) + 1
    return max(0, rows - len(re.findall(r"\\(?:nonumber|notag)\b", body)))


# --- X302: is the equation part of a sentence? -----------------------------------------

# "e.g.", "i.e.", "Eq.", "Fig.", an initial: a full stop that is not the end
# of a sentence.
_ABBREV_STOP = re.compile(
    r"(?:\b(?:e\.g|i\.e|cf|vs|etc|et al|Eq|Eqs|Fig|Figs|Ref|Refs|No|resp|"
    r"approx|ca|viz)\.|\b[A-Z]\.)$")


@rule("X302", "equation-not-in-sentence", Category.CONVENTION,
      "A displayed equation that is not part of a sentence.",
      "An equation is a clause of the sentence around it: the words before "
      "it lead in ('the force of infection is') and the words after it "
      "interpret it ('where beta is'). When the sentence before ends with a "
      "full stop, the equation floats in on its own, unannounced, and the "
      "reader has to guess what it is for. Introduce it, display it, then "
      "interpret it.",
      plain=("The sentence before this equation ends with a full stop, so "
             "the equation stands alone. Make it part of a sentence: lead "
             "in with words like 'is given by' or 'as', and follow it with "
             "what it means, such as 'where N is the population'."),
      source="§9.2")
def x302_equation_not_in_sentence(doc, document: Document):
    if document.kind == "latex":
        starts = [it.start for it in document.structure
                  if it.kind == "equation"]
    elif document.kind == "word":
        starts = list(_word_display_equations(document))
    else:
        return
    masked = document.masked
    for start in starts:
        before = masked[:start].rstrip()
        if not before:
            continue                       # nothing readable before it
        if before[-1] != "." or _ABBREV_STOP.search(before[-14:]):
            continue
        # "...} ." from a masked \cite or \ref is still the sentence's end.
        a, b = _word_near(document, start, start)
        yield Suggestion(
            message="This equation starts after a full stop — make it part "
                    "of a sentence (lead in, display, then interpret).",
            start=a, end=b)


# A displayed equation's paragraph in Word, once the equation object is
# masked: nothing, or its number ("\t(3)", "(3a)").
_EQ_NUMBER_ONLY = re.compile(r"^\s*(?:\(?\d{1,3}[a-z]?\)?)?\s*$")
# Function names that are maths, not words, in a typed equation.
_MATH_WORDS = frozenset(
    "log ln exp sin cos tan sinh cosh tanh max min arg lim sup inf det "
    "diag var cov dt dx dy ds du".split())


def _equation_paragraph(text: str) -> bool:
    """A Word paragraph that IS an equation written as text: a relation
    sign and no ordinary word. The add-in reads paragraph text only, so an
    equation object arrives in its linear form ("R0 = βS/N"); a PDF
    conversion flattens one the same way."""
    text = text.strip()
    if not text or len(text) > 240 or not _RELATION.search(text):
        return False
    return not any(w.lower() not in _MATH_WORDS
                   for w in re.findall(r"[A-Za-z]{2,}", text))


def _word_display_equations(document: Document):
    """Start offsets of the paragraphs that are a displayed equation: an
    equation object on its own (an uploaded .docx, where the reader masks
    it), or a paragraph of maths written as text (the add-in). An equation
    inside a sentence's paragraph is inline and never judged here."""
    offs = document.para_offsets
    objects = [it.start for it in document.structure if it.kind == "equation"]
    for i, off in enumerate(offs):
        end = offs[i + 1] - 2 if i + 1 < len(offs) else len(document.original)
        text = document.original[off:end]
        if not text.strip() or document.in_table(off):
            continue
        if any(off <= s < end for s in objects):
            if _EQ_NUMBER_ONLY.match(document.masked[off:end]):
                yield off
        elif _equation_paragraph(text):
            yield off


# --- X401: does the number quoted from a table appear in it? ------------------------

_VALUE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![.\d])(\s*\\?%)?")


def _values(text: str) -> list[tuple[str, float, int]]:
    """(as written, value, decimals) for decimals and percentages."""
    out = []
    for m in _VALUE.finditer(text):
        whole, frac, pct = m.group(1), m.group(2) or "", m.group(3)
        if not frac and not pct:
            continue                 # counts, years, ids: too often derived
        v = float(whole.replace(",", "") + frac)
        out.append((m.group(0).strip(), v, len(frac) - 1 if frac else 0))
    return out


def _in_table(value: float, decimals: int, table_text: str) -> bool:
    for _, v, d in _values(table_text) + [
            (None, float(x), 0) for x in re.findall(r"(?<![\w.])\d+(?![\d.])",
                                                    table_text)]:
        if abs(v - value) < 1e-9:
            return True
        # The text may round what the table reports: 0.4321 -> 0.43.
        if d > decimals and abs(round(v, decimals) - value) < 1e-9:
            return True
    return False


@rule("X401", "number-not-in-table", Category.CORRECTION,
      "A number quoted with 'Table N' that Table N does not contain.",
      'When a sentence cites a table and quotes a figure from it, the '
      'reader will look for that number in the table. A mismatch is '
      'usually a typo, a value from an older run, or a number from '
      'another table. Derived numbers (differences, ratios) are worth a '
      'word saying so.',
      plain=('This sentence cites a table and quotes a number, but that number '
             'is not in the table. It may be a typo, an old value, or a number '
             'from a different table. If you calculated it from the table, say '
             'so.'),
      source="§6",
      scope="document")
def x401_number_not_in_table(doc, document: Document):
    st = structure_of(document)
    floats_cited: dict = {}
    for m, fs in _text_mentions(st):
        floats_cited.setdefault(m.start, []).extend(fs)
    if not floats_cited:
        return
    for sent in doc.sents:
        a, b = sent.start_char, sent.end_char
        cited = [f for pos, fs in floats_cited.items() if a <= pos < b
                 for f in fs]
        if not cited:
            continue
        kinds = {f.kind for f in cited}
        tables = {id(f): f for f in cited if f.kind == "table"}
        # One table and nothing else: then the number must come from it.
        if kinds != {"table"} or len(tables) != 1:
            continue
        (t,) = tables.values()
        table_text = document.original[t.start:t.end]
        # A percentage quoted from a table of counts is derived, not
        # copied: only judge the kinds of number the table itself holds.
        has_pct = "%" in table_text
        has_dec = bool(re.search(r"\d\.\d", table_text))
        text = document.masked[a:b]
        if _AGGREGATE.search(text):
            continue                 # "altogether 99.9%": summed, not quoted
        for m in _VALUE.finditer(text):
            vals = _values(m.group(0))
            if not vals:
                continue
            written, value, decimals = vals[0]
            if not (has_pct if "%" in written else has_dec):
                continue
            # A level, not a result: "95% CI", "p < 0.05", "alpha = 0.05".
            if (_LEVEL_AFTER.match(text, m.end())
                    or _LEVEL_BEFORE.search(text[max(0, m.start() - 12):
                                                 m.start()])):
                continue
            if _in_table(value, decimals, table_text):
                continue
            shown = written.replace("\\%", "%")
            yield Suggestion(
                message=f"{shown} is not in {t.name} — a typo, an older "
                        "value, or a number from elsewhere?",
                start=a + m.start(), end=a + m.start() + len(written))


_AGGREGATE = re.compile(
    r"\b(?:altogether|in total|overall|combined|together|cumulative|"
    r"sum of|of all)\b", re.IGNORECASE)
_LEVEL_AFTER = re.compile(
    r"\s*(?:\\?%)?\s*(?:CI|CrI|UI|PI|HDI|confidence|credible|uncertainty|"
    r"prediction|significance)\b", re.IGNORECASE)
_LEVEL_BEFORE = re.compile(r"(?:\bp|\bP|α|alpha|level of)\s*[<>=≤≥]?\s*$")


# --- X501: a heading style on body text -------------------------------------------

@rule("X501", "heading-style-on-body-text", Category.CORRECTION,
      "A paragraph of body text formatted with a heading style.",
      "Word builds the navigation pane, the table of contents and a "
      "journal's section structure from heading styles. A paragraph of "
      "body text in a heading style puts the whole paragraph into all "
      "three, and a heading run into its first paragraph (common after "
      "converting a PDF) hides where the section starts.",
      plain=('This paragraph of normal text has a heading style. Word uses '
             'heading styles to build the table of contents and the navigation '
             'pane, so this whole paragraph will appear there. Give it a body '
             'style.'),
      source="Word",
      scope="document")
def x501_heading_style_on_body(doc, document: Document):
    if document.kind != "word":
        return
    for item in document.structure:
        if item.kind != "styled_body":
            continue
        text = document.original[item.start:item.end]
        n = len(text.split())
        a, b = _anchor(document, item.start, item.end, limit=60)
        if item.label == "run-in":
            msg = ("The heading runs into its first paragraph: "
                   f"{n} words carry the heading style. Put the heading on "
                   "its own line and give the text a body style.")
        else:
            msg = (f"This paragraph has a heading style but holds {n} words "
                   "of body text — give it a body style (or make it a "
                   "table, if it is one).")
        yield Suggestion(message=msg, start=a, end=b)
