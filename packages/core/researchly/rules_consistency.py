"""Consistency checks across a whole document (S2b; owner decision P2):
abbreviations, numbers and units, spelling of compounds.

Each rule compares the document with itself, never with a house style:
"5 %" is not wrong, but "5 %" here and "5%" there is. A document that is
consistent passes whichever convention it chose.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from . import lexicons as lx
from . import spelling
from .document import Document
from .engine import Category, Suggestion, rule

# "full name (ACR)": an abbreviation being defined.
_DEFINED = re.compile(r"\(\s*([A-Z][A-Za-z0-9-]{1,9}?)s?\s*\)")


def _is_acronym(token: str) -> bool:
    if _PANELS.fullmatch(token):
        return False                     # "(A-C)": panels A to C
    return sum(c.isupper() for c in token) >= 2 and not token.isdigit()


_PANELS = re.compile(r"[A-Z]\s*[-–—]\s*[A-Z]")
# A reference entry, not prose: a definition in a cited title is the
# cited paper's, not the author's.
_REFERENCE_ENTRY = re.compile(
    r"\bet al\.|\[Internet\]|\[cited\b|\bdoi\b|https?://|"
    r"\b(?:19|20)\d\d\s*(?:[A-Z][a-z]{2})?\s*;\s*\d+")


def _starts_new_part(document: Document, a: int, b: int) -> bool:
    """A new abstract or introduction between two definitions: a new
    chapter or paper, where defining an abbreviation again is right."""
    return any(a < h.start < b and h.section in ("abstract", "introduction")
               for h in document.headings)


def _long_form(short: str, before: str) -> str | None:
    """The words that `short` abbreviates at the end of `before`, by
    Schwartz & Hearst's (2003) algorithm: the short form's characters are
    found right to left in the text before it, its first character at the
    start of a word. None when they are not there: "A(H1N1)" or a panel
    list "(D-F)" is notation, not a definition."""
    s, i = len(short) - 1, len(before) - 1
    while s >= 0:
        c = short[s].lower()
        if not c.isalnum():
            s -= 1
            continue
        while i >= 0 and (before[i].lower() != c or (
                s == 0 and i > 0 and before[i - 1].isalnum())):
            i -= 1
        if i < 0:
            return None
        i -= 1
        s -= 1
    start = before.rfind(" ", 0, i + 1) + 1
    long = before[start:].strip()
    return long if len(long.split()) >= 2 or "-" in long else None


_IN_CAPTION = re.compile(
    r"(?:^|\n|[.!?]\s+)(?:Fig(?:ure)?\.?|Table)\s*S?\d+(?:\.\d+)*[.:]?\s"
    r"(?:[^.\n]|\.\d)*$")


def _definitions(document: Document) -> dict:
    """Where each abbreviation is defined ("full name (ACR)"), captions
    excepted: a caption defines its abbreviations again on purpose."""
    out = defaultdict(list)
    text = document.masked
    captions = [(i.start, i.end) for i in document.structure
                if i.kind == "caption"]
    for m in _DEFINED.finditer(text):
        if any(a <= m.start() < b for a, b in captions):
            continue                     # a LaTeX or Word caption
        acr = m.group(1)
        if (not _is_acronym(acr) or acr in lx.ACRONYM_ALLOWLIST
                or m.start() == 0 or not text[m.start() - 1].isspace()):
            continue
        window = text[max(0, m.start() - 12 * len(acr) - 20):m.start()]
        if _long_form(acr, window.rstrip()) is None:
            continue
        # In a caption: "Figure 3.9 ... (CMFB)" with no full stop between.
        if _IN_CAPTION.search(text[max(0, m.start() - 250):m.start()]):
            continue
        if _REFERENCE_ENTRY.search(text, max(0, m.start() - 150),
                                   m.end() + 150):
            continue
        out[acr].append((m.start(1), m.start(1) + len(acr)))
    return out


# A definition this far from the last one may be repeated for a reader who
# skipped ahead (about 3,000 words: another chapter).
_REDEFINE_AFTER = 20_000


@rule("F612", "abbreviation-defined-twice", Category.CONVENTION,
      "An abbreviation defined again after it was already defined.",
      'Define a term once, the first time you use it, then use it '
      'consistently. A second definition makes the reader wonder whether '
      'it means something new. A new chapter or paper (after its own '
      'abstract or introduction) may define it again.',
      plain=('This abbreviation was already explained earlier in the document. '
             'Explaining it again makes the reader wonder whether it now means '
             'something different. Define it once, at first use.'),
      source="§9.1",
      scope="document")
def f612_defined_twice(doc, document: Document):
    for acr, spans in _definitions(document).items():
        for (a0, _), (a, b) in zip(spans, spans[1:]):
            if document.section_at(a) == "abstract" or \
                    document.section_at(a0) == "abstract":
                continue                 # the abstract stands alone
            if _starts_new_part(document, a0, a) or a - a0 > _REDEFINE_AFTER:
                continue
            yield Suggestion(
                message=f"'{acr}' was already defined earlier — define it "
                        "once, at first use?",
                start=a, end=b)


@rule("F613", "abbreviation-rarely-used", Category.PREFERENCE,
      "An abbreviation defined but then used once or not at all.",
      'An abbreviation costs the reader a definition to hold in mind; it '
      'pays back only when used often. Defined and then used once or not '
      'at all, the full term is easier to read.',
      plain=('You defined this abbreviation but then hardly used it. An '
             'abbreviation only helps when it appears often. If it appears once '
             'or twice, the full words are easier to read.'),
      source="§9.1",
      scope="document")
def f613_rarely_used(doc, document: Document):
    text = document.masked
    for acr, spans in _definitions(document).items():
        a, b = spans[0]
        uses = len(re.findall(rf"(?<![\w-]){re.escape(acr)}s?(?![\w-])",
                              text[b:])) - (len(spans) - 1)
        if uses <= 1:
            yield Suggestion(
                message=f"'{acr}' is used {'once' if uses == 1 else 'nowhere'}"
                        " after its definition — spell the term out instead?",
                start=a, end=b)


# --- numbers and units -------------------------------------------------------------

_UNITS = ("%", "°C", "mg", "kg", "mL", "ml", "µg", "μg", "ng", "km", "cm",
          "mm", "kDa", "Hz", "kHz", "mmHg")
_UNIT_RX = re.compile(
    r"(?<![\w.])\d+(?:[.,]\d+)?( ?)(" + "|".join(re.escape(u) for u in
                                              sorted(_UNITS, key=len,
                                                     reverse=True))
    + r")(?![A-Za-z])")


@rule("N101", "number-unit-spacing-mixed", Category.CONVENTION,
      "A unit written with and without a space after the number.",
      "Journals differ on '5%' versus '5 %' and '37°C' versus '37 °C' "
      '(the SI Brochure puts a space before every unit, % included), but '
      'within one document the choice should not change.',
      plain=("You write units with a space in some places ('5 %') and without in "
             "others ('5%'). Both are accepted, but pick one and keep it the "
             'same throughout.'),
      source="SI",
      scope="document")
def n101_unit_spacing(doc, document: Document):
    text = document.masked
    found = defaultdict(list)
    for m in _UNIT_RX.finditer(text):
        unit = m.group(2).lower().replace("μ", "µ")
        found[unit].append((m.group(1) == " ", m.start(), m.end()))
    for unit, uses in found.items():
        spaced = sum(1 for s, _, _ in uses if s)
        if spaced == 0 or spaced == len(uses):
            continue
        minority = spaced < len(uses) - spaced
        odd = [(a, b) for s, a, b in uses if s == minority]
        majority = len(uses) - len(odd)
        a, b = odd[0]
        others = f"{majority} other{'s' if majority > 1 else ''}"
        if minority:
            msg = (f"'{text[a:b]}' has a space before the unit; {others} "
                   f"{'do' if majority > 1 else 'does'} not — pick one style.")
        else:
            msg = (f"'{text[a:b]}' has no space before the unit; {others} "
                   f"{'have' if majority > 1 else 'has'} one — pick one style.")
        yield Suggestion(message=msg, start=a, end=b)


def _times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


_YEAR = re.compile(r"(1[89]|20)\d\d\b")


@rule("N102", "sentence-starts-with-numeral", Category.CONVENTION,
      "A sentence that begins with a numeral.",
      'A sentence should not begin with a numeral: spell the number out '
      "('Twelve patients') or rephrase so it comes later ('Of the 312 "
      "patients'). Years are tolerated by most styles.",
      plain=('This sentence starts with a number written in digits. Most styles '
             "ask you to spell it out ('Twelve patients') or rephrase so it "
             "comes later ('Of the 312 patients'). Years at the start are fine."),
      source="AMA")
def n102_sentence_numeral(doc, document: Document):
    for sent in doc.sents:
        toks = [t for t in sent if not t.is_space]
        if len(toks) < 4:
            continue                     # a list marker, a table cell
        first = toks[0]
        if not (first.text[0].isdigit() and first.like_num):
            continue
        # A sentence: the number counts words ("12 patients were ..."),
        # in prose, not a table row or a contents line.
        if not toks[1].is_lower or not toks[1].is_alpha:
            continue
        words = sum(1 for t in toks if t.is_alpha)
        if words < 5 or sum(1 for t in toks if t.like_num) > len(toks) / 4:
            continue
        if _YEAR.fullmatch(first.text) or toks[1].text in (".", ")", ":"):
            continue                     # a year; a numbered list item
        if document.in_table(first.idx):
            continue
        # "3 Methods" is a numbered heading that lost its line break.
        if any(t.is_alpha and t.is_title for t in toks[1:3]) and \
                not any(t.pos_ in ("VERB", "AUX") for t in toks):
            continue
        if not any(t.pos_ in ("VERB", "AUX") for t in toks):
            continue                     # a fragment, not a sentence
        yield Suggestion(
            message="Starts with a numeral — spell it out, or rephrase so "
                    "the number comes later?",
            start=first.idx, end=first.idx + len(first.text))


# --- compounds written two ways ----------------------------------------------------

# Open forms with a different meaning or a verb use: "set up" (verb) vs
# "setup" (noun), "may be" vs "maybe", "every day" vs "everyday".
_PARTICLES = {"up", "out", "down", "in", "on", "off", "over", "back",
              "away", "about", "through"}
# "not able" is not "notable", "an other" not "another": an open form
# whose first word is a function word is two words, not a compound.
_FUNCTION_WORDS = {"not", "no", "a", "an", "the", "in", "on", "at", "to",
                   "be", "by", "for", "with", "of", "or", "and", "as", "is",
                   "it", "any", "some", "every", "all", "may", "can", "how",
                   "what", "who", "where", "when", "there", "here", "so",
                   "per", "our", "we", "my", "his", "her", "its", "one"}
_NOT_COMPOUNDS = {"into", "onto", "maybe", "everyday", "anyone", "cannot",
                  "however", "another", "overall", "whatever", "therefore",
                  "nobody", "someone", "sometime", "sometimes", "anyway",
                  "within", "without", "together", "whereas", "upon",
                  "itself", "himself", "herself", "themselves", "otherwise",
                  "meantime", "everyone", "anything", "something", "nothing",
                  "everything", "nevertheless", "nonetheless", "moreover",
                  "furthermore", "whenever", "wherever", "thereby",
                  "hereafter", "thereafter", "forthcoming", "inasmuch"}
_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)?")


@rule("W211", "compound-spelled-two-ways", Category.CONVENTION,
      "The same compound written closed and open (or hyphenated).",
      "'dataset' and 'data set', 'healthcare' and 'health care', "
      "'timepoint' and 'time point': each is fine, but one document "
      'should pick one, or the reader wonders whether two things are '
      'meant.',
      plain=("This word appears both as one word and as two, like 'dataset' and "
             "'data set'. Both are fine, but use one form throughout so readers "
             'do not think you mean two different things.'),
      source="§9.1",
      scope="document")
def w211_compound_two_ways(doc, document: Document):
    text = document.masked
    words = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(text)]
    closed = Counter(w.lower() for w, _, _ in words if "-" not in w)
    split_forms = defaultdict(list)          # "dataset" -> spans of "data set"
    for (w1, a, _), (w2, _, b) in zip(words, words[1:]):
        if text[a:b].count("\n") or "-" in w1 or "-" in w2:
            continue
        if a and text[a - 1] == "-":
            continue                     # "28-day time": not "day time"
        if text[a + len(w1):b - len(w2)] != " ":
            continue
        if w1.lower() in _FUNCTION_WORDS:
            continue
        split_forms[(w1 + w2).lower()].append((a, b, w2.lower()))
    for w, a, b in words:
        if "-" in w:
            left, right = w.lower().split("-", 1)
            split_forms[left + right].append((a, b, right))
    for joined, spans in split_forms.items():
        n_closed = closed.get(joined, 0)
        if not n_closed or len(joined) < 6 or joined in _NOT_COMPOUNDS:
            continue
        spans = [(a, b) for a, b, right in spans
                 if right not in _PARTICLES and len(right) >= 3
                 and b - a - len(right) - 1 >= 3]
        if not spans:
            continue
        if (not spelling.known_with_fallbacks(joined)
                and joined not in spelling.domain_terms()):
            continue          # not a word: a typo or two words run together
        if len(spans) <= n_closed:
            odd = spans                  # the split form is the minority
            other = f"'{joined}' ({_times(n_closed)})"
        else:
            odd = [m.span() for m in re.finditer(
                rf"(?<![\w-]){joined}(?![\w-])", text, re.IGNORECASE)]
            first = text[spans[0][0]:spans[0][1]]
            other = f"'{first}' ({_times(len(spans))})"
        if not odd:
            continue          # only inside longer compounds ("a-b-c")
        a, b = odd[0]
        yield Suggestion(
            message=f"'{text[a:b]}' here, {other} elsewhere — pick one "
                    "spelling.",
            start=a, end=b)
