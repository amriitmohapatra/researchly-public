"""Locating a suggestion in Word paragraphs (S3). Synthetic text only."""

from researchly.document import Document
from researchly.wordloc import coverage, locate

PARAS = [{"text": "Results", "style": "Heading 1"},
         {"text": "We saw the the rise; then the the fall."},
         {"text": "Cell", "kind": "table"}]


def test_second_occurrence_in_its_paragraph():
    doc = Document.from_word(PARAS)
    t = doc.original
    second = t.index("the the", t.index("the the") + 1)
    loc = locate(doc, PARAS, second, second + 7)
    assert loc == {"paragraph": 1, "start": 26, "end": 33,
                   "snippet": "the the", "occurrence": 1, "exact": True}


def test_long_span_is_not_exact():
    long = "word " * 80
    paras = [{"text": long}]
    doc = Document.from_word(paras)
    loc = locate(doc, paras, 0, len(long))
    assert loc["exact"] is False and len(loc["snippet"]) == 180


def test_span_clamped_to_its_paragraph():
    doc = Document.from_word(PARAS)
    start = doc.para_offsets[1]
    loc = locate(doc, PARAS, start, start + 10_000)
    assert loc["end"] == len(PARAS[1]["text"])


def test_coverage_says_what_was_not_read():
    doc = Document.from_word(PARAS)
    c = coverage(PARAS, doc)
    assert c["paragraphs"] == 3 and c["table_paragraphs"] == 1
    assert "footnotes" in c["not_checked"]
