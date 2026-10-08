"""Where a suggestion sits in a Word document (Office JS paragraphs).

Word has no offset-addressable API: the add-in finds a span again by
searching its paragraph. Shared by the hosted engine (/v1/analyze-word) and
the local add-in server, so both answer the same way.
"""

from __future__ import annotations

from .document import Document

# What Office JS `body.paragraphs` never hands over, stated plainly: silence
# would read as "nothing to flag" rather than "not looked at".
NOT_CHECKED = ("footnotes", "endnotes", "headers and footers", "text boxes",
               "comments")

# Word's search() refuses longer needles.
MAX_NEEDLE = 255


def locate(doc: Document, paragraphs: list[dict], start: int,
           end: int) -> dict:
    """{paragraph, start, end, snippet, occurrence, exact} for a span of
    `doc` (built by Document.from_word from `paragraphs`).

    The snippet is the FULL span when Word can search for it (a truncated
    one can match somewhere else); the occurrence is counted with that same
    string, so "the 2nd 'the the' in paragraph 4" means the same to both
    sides. When an exact literal cannot be handed over, `exact` says so.
    """
    para, start_in = doc.locate(start)
    text = paragraphs[para].get("text") or ""
    end_in = max(start_in, min(end - doc.para_offsets[para], len(text)))
    span = text[start_in:end_in]
    exact = bool(span) and len(span) <= MAX_NEEDLE and "^" not in span
    snippet = span if exact else span[:180].replace("^", "")
    occurrence = text[:start_in].count(snippet) if snippet else 0
    return {"paragraph": para, "start": start_in, "end": end_in,
            "snippet": snippet, "occurrence": occurrence, "exact": exact}


def coverage(paragraphs: list[dict], doc: Document) -> dict:
    return {"paragraphs": len(paragraphs),
            "table_paragraphs": len(getattr(doc, "table_spans", [])),
            "not_checked": list(NOT_CHECKED)}
