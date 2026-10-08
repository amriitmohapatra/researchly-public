"""S001 — the basic spelling layer (SymSpell-backed), precision-guarded.

This is the 'commodity' tier deliberately deferred in Phase 1 and added
once a maintained open-source component could be integrated rather than
rebuilt (symspellpy, MIT). Grammar-proper (agreement, articles) is the
optional LanguageTool tier in rules_grammar.py.

Implementation note: words are scanned with a regex over the masked text
rather than spaCy tokens — the tokenizer SPLITS some typos ("thiss" →
"this"+"s"), which would hide them from a token-based scan.
"""

from __future__ import annotations

import re
from collections import Counter

from . import lexicons as lx
from . import spelling
from .document import Document
from .engine import Category, Suggestion, rule

MIN_LEN = 3
WORD_RX = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _sentence_start(text: str, start: int) -> bool:
    """Is this word the first of a sentence (or of the text/line)?"""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in ".!?\n"


# The halves of a word broken at a line end by a PDF: "effec-" + "tive".
# At most a blank line between them: a masked line is a run of spaces.
_BROKEN_AFTER = re.compile(
    r"-[ \t]{0,3}\n(?:[ \t]{0,3}\n)?[ \t]{0,3}([a-z]+)\b")
_BROKEN_BEFORE = re.compile(
    r"[A-Za-z]-[ \t]{0,3}\n(?:[ \t]{0,3}\n)?[ \t]{0,3}\Z")


def _in_latin_phrase(text: str, m) -> bool:
    """"ad valorem", "per capita": the word and a neighbour form a phrase."""
    before = re.search(r"([A-Za-z]+)[\s-]+$", text[max(0, m.start() - 20):m.start()])
    after = re.match(r"[\s-]+([A-Za-z]+)", text[m.end():m.end() + 20])
    w = m.group(0).lower()
    return ((before is not None
             and f"{before.group(1).lower()} {w}" in lx.LATIN_PHRASES)
            or (after is not None
                and f"{w} {after.group(1).lower()}" in lx.LATIN_PHRASES))


def _in_url_like(text: str, start: int, end: int) -> bool:
    prev = text[start - 1] if start > 0 else " "
    nxt = text[end] if end < len(text) else " "
    if prev in "@/_-" or nxt in "@/_":
        return True
    if text.startswith("://", end):                   # "https://..."
        return True
    # "example.com" — a dot immediately followed by another letter
    if nxt == "." and end + 1 < len(text) and text[end + 1].isalpha():
        return True
    return False


# What follows a surname in a citation or reference entry: initials
# ("Lau H, Khosrawipour V", "Zhang, Y.") or "et al". A dictionary cannot
# judge a name, and at a sentence start (a numbered reference, "Ruan et
# al. found") the proper-noun guard in s001 does not apply (P31).
_AUTHOR_NAME = re.compile(
    r",?\s+(?:et\s+al\b|[A-Z]{1,3}(?:[,.;]|\s+[A-Z][a-z])|[A-Z]\.)")


@rule("S001", "spelling", Category.CORRECTION,
      "Possible misspelling (SymSpell dictionary + scientific lexicon).",
      'Spelling against a frequency dictionary plus a scientific lexicon '
      '(seroprevalence, covariates, nowcasting are not errors here). '
      'Proper nouns, acronyms, UK/US variants, and terms you use '
      'repeatedly are skipped. A false alarm on your own terminology: '
      "'Add to dictionary' on the card teaches it the word.",
      plain=('This word is not in the dictionary, so it may be a typo. '
             'Scientific terms, names and abbreviations are usually recognised. '
             'If it is a real word you use, add it to your dictionary from this '
             'card and it will not be flagged again.'),
      source="symspellpy",
      tier="spelling", fix_safety="review")
def s001_spelling(doc, document: Document):
    text = document.masked
    domain = spelling.domain_terms()
    cfg_words: list[str] = getattr(document, "extra_dictionary", []) or []
    user = spelling.user_dictionary(cfg_words)

    words = list(WORD_RX.finditer(text))
    # words the author uses 3+ times are their vocabulary, not typos
    counts = Counter(m.group(0).lower() for m in words)

    for m in words:
        w = m.group(0)
        if "'" in w:
            continue
        # A word a PDF broke across a line ("effec-\ntive"): judge the whole
        # word, once, on its first half (P33).
        if _BROKEN_BEFORE.search(text, max(0, m.start() - 12), m.start()):
            continue
        broken = _BROKEN_AFTER.match(text, m.end())
        if broken:
            joined = w + broken.group(1)
            if spelling.known_with_fallbacks(joined.lower()):
                yield Suggestion(
                    message=f"One word broken across a line — join it: "
                            f"'{joined}'.",
                    start=m.start(), end=broken.end(1), replacement=joined)
                continue
        if len(w) < MIN_LEN:
            continue
        if w.isupper():                       # acronyms → F601's business
            continue
        lower = w.lower()
        if lower in domain or lower in user:
            continue
        if w.upper() in lx.ACRONYM_ALLOWLIST:
            continue
        if counts[lower] >= 3:
            continue
        if _in_url_like(text, m.start(), m.end()):
            continue
        if lower in lx._LATIN_WORDS and _in_latin_phrase(text, m):
            continue
        # "mis-ordered", "non-zero", "co-circulating": a prefix before a
        # hyphen is half of a compound, not a word on its own.
        if text[m.end():m.end() + 1] == "-" and \
                lower in spelling.DERIVATIONAL_PREFIXES:
            continue
        capitalized = w[0].isupper()
        if capitalized and not _sentence_start(text, m.start()):
            continue                          # likely a proper noun
        if capitalized and _AUTHOR_NAME.match(text, m.end()):
            continue                          # "Lau H, ...", "Ruan et al."
        if spelling.known_with_fallbacks(lower):
            continue

        scored = spelling.suggest_with_distance(lower, top_n=3)
        # A capitalized unknown at a sentence start may be a NAME opening
        # the sentence ("Kieshha and colleagues…"). Only flag it when a
        # distance-1 correction exists ("Thiss"→"this") — anything farther
        # is more likely a name than a typo.
        if capitalized and (not scored or scored[0][1] > 1):
            continue
        candidates = [t for t, _ in scored]
        if candidates:
            top = spelling.match_case(candidates[0], w)
            rest = (f" (also: {', '.join(candidates[1:])})"
                    if len(candidates) > 1 else "")
            msg = f"Did you mean '{top}'?{rest}"
            repl = top
        else:
            msg = ("Not in any dictionary — if this is your term, "
                   "`researchly dict add` it.")
            repl = None
        yield Suggestion(
            message=msg,
            start=m.start(), end=m.end(),
            replacement=repl)
