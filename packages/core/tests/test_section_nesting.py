"""Nested headings inherit their parent's section (P28, P29 parity).

The owner's methods report had "Priors" and "Solver" subsections under
Methods; each reset the section to "other", so passive-voice advice meant
for Discussion fired in Methods. The real-document bench showed the same
bug as G104 firing ~2x more in docx/tex renderings than in plain text.

Synthetic sentences only (CLAUDE.md).
"""

import pytest

from researchly import api
from researchly.document import Document, is_section_name
from researchly.engine import check
from researchly.ingest import load_bytes
from ingest_fixtures import docx_bytes, para

NLP = api.get_nlp()
AGENT = "The incidence curve was smoothed by the authors before fitting."


def sections(doc):
    return [(h.text, h.section) for h in doc.headings]


def rule_sections(doc, rule_id):
    return [s.section for s in check(doc, NLP, show_preferences=True,
                                     disabled={"LT001"})
            if s.rule_id == rule_id]


# --- what counts as a plain section name -------------------------------------

@pytest.mark.parametrize("title,named", [
    ("Methods", True),
    ("Materials and methods", True),
    ("3.2 Statistical analysis", True),
    ("Chapter 2: Results", True),
    ("Strengths and limitations", True),
    ("II. Discussion", True),
    ("A model of measles transmission", False),
    ("Model fit", False),
    ("Principal findings", False),     # a Discussion subsection in BMJ style
    ("Priors", False),
    ("", False),
])
def test_is_section_name(title, named):
    assert is_section_name(title) is named


# --- LaTeX ---------------------------------------------------------------------

def test_subsection_without_a_keyword_inherits_methods():
    src = ("\\section{Methods}\nWe describe the model.\n"
           "\\subsection{Priors}\n" + AGENT + "\n"
           "\\subsection{Solver settings}\nThe solver used adaptive steps.\n"
           "\\section{Discussion}\n" + AGENT + "\n")
    doc = Document.from_text(src, "latex")
    assert sections(doc) == [
        ("Methods", "methods"), ("Priors", "methods"),
        ("Solver settings", "methods"), ("Discussion", "discussion")]
    # G104 (passive with a by-agent) stays silent in Methods, fires after.
    assert rule_sections(doc, "G104") == ["discussion"]


def test_stray_keyword_under_a_section_name_does_not_switch():
    src = ("\\section{Results}\nThe epidemic peaked in week 12.\n"
           "\\subsection{Model fit}\n" + AGENT + "\n"
           "\\subsubsection{Data quality}\nReporting was complete.\n")
    doc = Document.from_text(src, "latex")
    assert sections(doc) == [("Results", "results"),
                             ("Model fit", "results"),
                             ("Data quality", "results")]
    assert rule_sections(doc, "G104") == ["results"]


def test_named_subsection_keeps_its_own_section():
    src = ("\\section{Discussion}\nThe estimates agree.\n"
           "\\subsection{Strengths and limitations}\nThe sample was small.\n"
           "\\subsection{Comparison with other studies}\nThey agree.\n"
           "\\section{Conclusion}\nDone.\n")
    doc = Document.from_text(src, "latex")
    assert sections(doc) == [
        ("Discussion", "discussion"),
        ("Strengths and limitations", "limitations"),
        ("Comparison with other studies", "discussion"),
        ("Conclusion", "conclusion")]


def test_topical_chapter_lets_its_sections_speak():
    src = ("\\chapter{A model of measles transmission}\nOverview.\n"
           "\\section{Background}\nMeasles spreads fast.\n"
           "\\section{Fitting procedure}\nWe fitted it.\n"
           "\\subsection{Priors}\nWeakly informative.\n"
           "\\section{Results}\nThe peak came early.\n"
           "\\subsection{Model fit}\nThe fit was close.\n"
           "\\chapter{Spatial heterogeneity}\nOverview.\n"
           "\\section{Discussion}\nIt matters.\n")
    doc = Document.from_text(src, "latex")
    assert sections(doc) == [
        ("A model of measles transmission", "methods"),
        ("Background", "introduction"),
        ("Fitting procedure", "methods"),      # own keyword ("fitting" →
        ("Priors", "methods"),                 #  none) falls back to parent
        ("Results", "results"),
        ("Model fit", "results"),
        ("Spatial heterogeneity", "other"),
        ("Discussion", "discussion")]


def test_sibling_after_nested_section_is_not_its_child():
    src = ("\\section{Methods}\nA.\n\\subsection{Priors}\nB.\n"
           "\\section{Sensitivity}\nC.\n")
    doc = Document.from_text(src, "latex")
    # "Sensitivity" is a top-level section of its own, not under Methods.
    assert sections(doc)[-1] == ("Sensitivity", "other")


def test_regex_fallback_reads_levels_too():
    # Unbalanced braces send the parser to the regex reader.
    src = ("\\section{Methods}\nThe {model was simple.\n"
           "\\subsection{Priors}\n" + AGENT + "\n")
    doc = Document.from_text(src, "latex")
    assert doc.warnings, "expected the regex fallback"
    assert sections(doc) == [("Methods", "methods"), ("Priors", "methods")]


# --- Markdown --------------------------------------------------------------------

def test_markdown_levels():
    src = ("# Results\n\nThe peak came early.\n\n## Model fit\n\n" + AGENT +
           "\n\n# Discussion\n\nIt matters.\n")
    doc = Document.from_text(src, "markdown")
    assert sections(doc) == [("Results", "results"), ("Model fit", "results"),
                             ("Discussion", "discussion")]
    assert [h.level for h in doc.headings] == [1, 2, 1]


# --- Word ----------------------------------------------------------------------

def test_word_heading_levels():
    doc = Document.from_word([
        {"text": "Methods for nowcasting dengue", "style": "Title"},
        {"text": "Introduction", "style": "Heading 1"},
        {"text": "Intro text."},
        {"text": "Methods", "style": "Heading 1"},
        {"text": "Priors", "style": "Heading 2"},
        {"text": AGENT},
    ])
    # The Title stands alone: it does not make the whole paper "methods".
    assert sections(doc) == [
        ("Methods for nowcasting dengue", "front"),
        ("Introduction", "introduction"), ("Methods", "methods"),
        ("Priors", "methods")]
    assert rule_sections(doc, "G104") == []


def test_docx_outline_levels_become_heading_levels():
    # A custom style with only an outline level, as some templates use.
    body = (para("Methods", style="berschrift1") + para("Body.") +
            para("Priors", outline=1) + para(AGENT))
    doc = load_bytes("chapter.docx", docx_bytes(body))
    assert [(h.text, h.level, h.section) for h in doc.headings] == [
        ("Methods", 1, "methods"), ("Priors", 2, "methods")]
    assert rule_sections(doc, "G104") == []


# --- plain text keeps its old behaviour ------------------------------------------

def test_plain_text_headings_stand_alone():
    doc = Document.from_text("Results\n\nThe peak came early.\n\n"
                             "Statistical analysis\n\nWe used a GLM.\n")
    assert [h.level for h in doc.headings] == [None, None]
    assert sections(doc) == [("Results", "results"),
                             ("Statistical analysis", "methods")]


# --- section-wide rules see their subsections -------------------------------------

FILLER = ("Dengue transmission varies between districts and seasons. "
          "Vector density follows rainfall with a short delay. ") * 6
GAP = ("However, the role of commuting in this variation remains unclear, "
       "and few studies have measured it directly.")


def test_d902_reads_the_whole_introduction():
    src = ("\\section{Introduction}\n" + FILLER + "\n"
           "\\subsection{Aims}\n" + GAP + "\n"
           "\\section{Methods}\nWe fitted the model.\n")
    doc = Document.from_text(src, "latex")
    assert rule_sections(doc, "D902") == []          # the gap is there


def test_d902_still_fires_without_a_gap():
    src = ("\\section{Introduction}\n" + FILLER + "\n"
           "\\subsection{Aims}\nWe estimate the effect of commuting.\n"
           "\\section{Methods}\nWe fitted the model.\n")
    doc = Document.from_text(src, "latex")
    assert rule_sections(doc, "D902") == ["introduction"]
