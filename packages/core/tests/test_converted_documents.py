"""A manuscript converted from PDF to Word (P33).

The owner's stress test was a working paper run through a PDF-to-Word
converter: headings run into their paragraphs, table rows in heading styles,
columns aligned with spaces, displayed equations flattened to symbols and
words broken across lines. Synthetic sentences only.
"""

import pytest

from researchly import api, spelling
from researchly.document import Document, layout_spans, split_run_in
from researchly.rules_grammar import SKIP_MISREAD_PREFIXES

NLP = api.get_nlp()

BODY = ("We fitted a transmission model to weekly case counts from three "
        "districts and compared the estimated reproduction numbers across "
        "the two seasons that the surveillance system covered in full.")


def analyse(doc: Document, rule_id: str):
    return [s for s in api.analyze(doc, nlp=NLP,
                                   show_preferences=True).suggestions
            if s.rule_id == rule_id]


def plain(text: str, rule_id: str):
    return analyse(Document.from_text(text), rule_id)


# --- headings that hold body text ---------------------------------------------------

@pytest.mark.parametrize("title,head", [
    ("2 Methods " + BODY, "2 Methods"),
    ("6 Conclusion This paper estimates the burden of dengue in the region "
     "and shows that most of it falls on adults.", "6 Conclusion"),
    ("3 Estimates of the Reproduction Number This section applies the "
     "method to the case counts of each district.",
     "3 Estimates of the Reproduction Number"),
])
def test_split_run_in(title, head):
    assert title[:split_run_in(title)].strip() == head


@pytest.mark.parametrize("title", [
    # a sentence in a heading style: no numbered heading to split off
    "Appendix Figure 4 compares the age distribution in the survey with "
    "that in the census.",
    # a table row in a heading style
    "1 Alpha district 0.12 0.30 2 Beta district 0.40 0.52 3 Gamma district",
])
def test_split_run_in_refuses(title):
    assert split_run_in(title) is None


def test_run_in_heading_is_split_and_flagged():
    doc = Document.from_word([
        {"text": "Abstract", "style": "Heading 1"},
        {"text": "We estimate the burden of dengue."},
        {"text": "2 Methods " + BODY, "style": "Heading 1"},
    ])
    h = doc.headings[-1]
    assert h.text == "2 Methods" and h.section == "methods"
    assert "We fitted a transmission model" in doc.masked   # checked as prose
    (x,) = analyse(doc, "X501")
    assert "runs into its first paragraph" in x.message


def test_table_row_in_a_heading_style_is_prose_not_a_heading():
    row = ("1 Alpha district 0.12 0.30 2 Beta district 0.40 0.52 3 Gamma "
           "district 0.33 0.61 4 Delta district 0.21 0.44 5 Epsilon "
           "district 0.18 0.27 6 Zeta district")
    doc = Document.from_word([{"text": "Results", "style": "Heading 1"},
                              {"text": row, "style": "Heading 1"}])
    assert [h.text for h in doc.headings] == ["Results"]
    (x,) = analyse(doc, "X501")
    assert "give it a body style" in x.message


def test_x501_quiet_on_ordinary_headings():
    doc = Document.from_word([
        {"text": "2.1 Estimation of the reproduction number",
         "style": "Heading 2"},
        {"text": BODY},
    ])
    assert analyse(doc, "X501") == []


# --- a PDF's layout: aligned columns and flattened equations ---------------------

def test_layout_lines_are_masked():
    text = ("Results\n\nThe table below lists the fixed effects.\n"
            "District FE          Yes        Yes       Yes\n"
            "d log y j t = (1 − ε)d log c j t + d log x t\n"
            "Time is indexed by t ∈ {0, 1}, and each firm j sells one good.\n")
    doc = Document.from_text(text)
    assert "Yes" not in doc.masked
    assert "d log y" not in doc.masked
    assert "each firm j sells one good" in doc.masked     # prose with maths
    assert len(layout_spans(text)) == 2


def test_doubled_words_in_a_layout_are_not_typos():
    assert plain("Methods\n\nAge Yes        Yes and the model.\n"
                 "We used s S and P P as shorthand. Region Yes Yes Yes "
                 "Yes.\n", "W207") == []


def test_doubled_word_still_flagged():
    (h,) = plain("Methods\n\nWe fitted the the model to the counts.\n",
                 "W207")
    assert h.text == "the the"


def test_urls_are_not_words():
    assert plain("Methods\n\nThe code is at https://www.example.org/zqlab "
                 "and qx@example.org.\n", "S001") == []


# --- a blank line ends a sentence ------------------------------------------------

def test_paragraph_break_ends_a_sentence():
    doc = NLP("Working Paper 12 Spring Term\n\nWe measured the cases.")
    assert len(list(doc.sents)) == 2


# --- spelling: words broken across a line, and the lexicon ----------------------

def test_word_broken_across_a_line_is_one_finding():
    hits = plain("Methods\n\nThe vaccine was effec-\ntive in every district "
                 "we studied.\n", "S001")
    assert len(hits) == 1 and hits[0].replacement == "effective"


def test_broken_word_not_joined_across_a_masked_line():
    text = ("Methods\n\nThe period-profit re-\n"
            "d log y j t = (1 − ε)d log c j t + d log x t\n"
            "elsewhere we drop the subscripts.\n")
    assert all(h.replacement != "reelsewhere"
               for h in plain(text, "S001"))


@pytest.mark.parametrize("word", ["winsorized", "equilibria", "premia",
                                  "transformative", "scatterplot", "iid"])
def test_lexicon_knows_common_statistics_words(word):
    assert word in spelling.domain_terms()


def test_diacritic_spellings_are_not_errors():
    assert "EN_DIACRITICS_REPLACE_" in SKIP_MISREAD_PREFIXES


# --- rules that misread a converted manuscript -----------------------------------

def test_w201_leverage_as_a_noun_is_quiet():
    assert plain("Methods\n\nFinancial leverage was high in 2021, and book "
                 "leverage fell.\n", "W201") == []


def test_w201_leverage_as_a_verb_fires():
    (h,) = plain("Methods\n\nWe leverage the weekly counts to fit the "
                 "model.\n", "W201")
    assert h.replacement == "use"


def test_g107_repeated_stack_is_one_card():
    stack = "district case count report"
    text = ("Methods\n\n" + " ".join(
        f"The {stack} arrived on day {d} of the month." for d in (2, 9, 16)))
    hits = plain(text, "G107")
    assert len(hits) == 1 and "used 3 times" in hits[0].message


def test_f601_quiet_on_a_title_in_capitals():
    assert plain("NATIONAL INSTITUTE OF TROPICAL RESEARCH 12 Main Road, "
                 "Springfield\n\nAbstract\n\nWe estimate the burden.\n",
                 "F601") == []


def test_typed_caption_in_a_body_style_is_a_caption():
    doc = Document.from_word([
        {"text": "Results", "style": "Heading 1"},
        {"text": "Table 1: Weekly counts by district and season."},
        {"text": "The counts rose in every district."},
    ])
    assert [i.kind for i in doc.structure] == ["caption"]
    (x,) = analyse(doc, "X101")
    assert "Table 1" in x.message


# --- appendix floats lettered A, B, C ... -----------------------------------------

def _word_doc(*paras):
    return Document.from_word(
        [{"text": "Results", "style": "Heading 1"}]
        + [p if isinstance(p, dict) else {"text": p} for p in paras])


def test_lettered_appendix_table_is_a_float():
    doc = _word_doc("The estimates are stable (Table A.1).",
                    {"text": "Appendix", "style": "Heading 1"},
                    "Table A.1: Estimates by district and season.")
    assert analyse(doc, "X101") == [] and analyse(doc, "X103") == []


def test_lettered_reference_to_a_missing_table():
    doc = _word_doc("The estimates are stable (Tables A.1 and A.3).",
                    {"text": "Appendix", "style": "Heading 1"},
                    "Table A.1: Estimates by district and season.")
    (h,) = analyse(doc, "X103")
    assert "Table A.3" in h.message


def test_continued_table_is_one_table():
    doc = _word_doc("The counts are listed in Table 2.",
                    "Table 2: Weekly counts by district.",
                    "Table 2: Weekly counts by district (continued)")
    assert analyse(doc, "X101") == []
    from researchly.rules_structure import structure_of
    assert len(structure_of(doc).floats) == 1


def test_caption_run_into_a_paragraph_is_not_a_missing_figure():
    doc = _word_doc("The relation is linear, as Figure 3 shows.",
                    "We repeat the fit by season. Figure 3: Weekly counts "
                    "against rainfall in each district.")
    assert analyse(doc, "X103") == []


def test_caption_on_its_own_line_inside_a_paragraph():
    doc = _word_doc("The comparison is shown in Table 4.\n"
                    "   Table 4: Spending by sector and year.")
    assert [i.kind for i in doc.structure] == ["caption"]


def test_styled_headings_suppress_guessed_ones():
    doc = Document.from_word([
        {"text": "Results", "style": "Heading 1"},
        {"text": "Fit statistics"},
        {"text": "Observations rose in every district."},
    ])
    assert [h.text for h in doc.headings] == ["Results"]


def test_data_appendix_is_an_appendix():
    from researchly.document import classify_heading
    assert classify_heading("C Data Appendix") == "appendix"
    assert classify_heading("Supplementary methods") == "appendix"


def test_a_table_row_is_not_a_plain_heading():
    doc = Document.from_text("Statistic       Value\n\nMethods\n\nWe fit.\n")
    assert [h.text for h in doc.headings] == ["Methods"]


# --- typed captions after the published-article run (P33) -------------------------

def test_list_of_figures_entry_is_not_a_caption():
    doc = _word_doc("Figure 1: Study area and districts ..... 12",
                    "Figure 2: Weekly counts\t14")
    assert doc.structure == []


def test_list_of_figures_style_is_not_a_caption():
    doc = Document.from_word([
        {"text": "Figure 1: Study area and districts",
         "style": "Table of Figures"},
        {"text": "Results", "style": "Heading 1"},
        {"text": "The districts are shown in Figure 1."}])
    assert doc.structure == []


def test_repeated_typed_caption_is_one_float():
    from researchly.rules_structure import structure_of
    doc = _word_doc("Figure 1: Study area and districts.",
                    "The districts are shown in Figure 1.",
                    "Figure 1: Study area and districts.")
    assert len(structure_of(doc).floats) == 1


def test_x104_judges_styled_captions_only():
    typed = _word_doc("Table 1: Weekly counts by district.",
                      "The counts rose (Table 1).")
    styled = _word_doc({"text": "Table 1: Weekly counts by district.",
                        "style": "Caption"},
                       "The counts rose (Table 1).")
    assert analyse(typed, "X104") == []
    assert len(analyse(styled, "X104")) == 1


def test_x301_counts_eqn():
    from researchly.rules_structure import _written_equation_numbers
    assert {"3", "4"} <= _written_equation_numbers("from Eqn. (3) and eqns 4")
