"""LaTeX masking by parser (researchly.ingest.latex).

The contract: `masked` is as long as the source, newlines stay put, every
character either survives unchanged or becomes a space, and only prose
survives. All text is synthetic.
"""

import random

import pytest

from researchly import api
from researchly.document import Document, _mask_latex
from researchly.engine import check
from researchly.ingest import load_bytes
from researchly.ingest.latex import mask_latex

NLP = api.get_nlp()


def masked(text):
    return Document.from_text(text, "latex").masked


def assert_offsets(src, out):
    assert len(out) == len(src)
    for a, b in zip(src, out):
        assert b == a or b == " ", (a, b)
        assert (a == "\n") == (b == "\n")


def flagged(text, rule_id, **kw):
    doc = Document.from_text(text, "latex")
    return [s for s in check(doc, NLP, show_preferences=True, **kw)
            if s.rule_id == rule_id]


# --- what is masked --------------------------------------------------------

@pytest.mark.parametrize("src,hidden", [
    ("Text % zqcomment here\nmore.", "zqcomment"),
    ("Rate $zqmath$ here.", "zqmath"),
    ("Rate \\(zqmath\\) here.", "zqmath"),
    ("Rate \\[zqmath\\] here.", "zqmath"),
    ("Rate $$zqmath$$ here.", "zqmath"),
    ("A\n\\begin{equation}zqmath\\end{equation}\nB.", "zqmath"),
    ("A\n\\begin{align*}x &= zqmath\\end{align*}\nB.", "zqmath"),
    ("A\n\\begin{gather}zqmath\\end{gather}\nB.", "zqmath"),
    ("A\n\\begin{multline}zqmath\\end{multline}\nB.", "zqmath"),
    ("A\n\\begin{eqnarray*}zqmath\\end{eqnarray*}\nB.", "zqmath"),
    ("A \\begin{tabular}{ll}zqcell & two\\\\\\end{tabular} B.", "zqcell"),
    ("A\n\\begin{verbatim}\nzqcode $ % {\n\\end{verbatim}\nB.", "zqcode"),
    ("A\n\\begin{lstlisting}[language=R]\nzqcode <- 1 % 2\n"
     "\\end{lstlisting}\nB.", "zqcode"),
    ("A\n\\begin{minted}{python}\nzqcode = {1: '$'}\n\\end{minted}\nB.",
     "zqcode"),
    ("As shown \\cite{zqkey}.", "zqkey"),
    ("As shown \\citep[see][p.~4]{zqkey,other}.", "zqkey"),
    ("As shown \\parencite{zqkey}.", "zqkey"),
    ("As \\textcite{zqkey} showed.", "zqkey"),
    ("See Figure~\\ref{fig:zqref}.", "zqref"),
    ("See \\eqref{eq:zqref}.", "zqref"),
    ("Here\\label{sec:zqlabel} we go.", "zqlabel"),
    ("Visit \\url{https://zqhost.org/a%20b} today.", "zqhost"),
    ("Visit \\href{https://zqhost.org/a%20b}{our page} today.", "zqhost"),
    ("A \\includegraphics[width=2cm]{zqimage.png} B.", "zqimage"),
    ("Some \\verb|zqcode$| text.", "zqcode"),
    ("Some \\lstinline{zqcode{x}} text.", "zqcode"),
    ("A \\hspace{2zqcm} B.", "zqcm"),
])
def test_non_prose_is_masked(src, hidden):
    out = masked(src)
    assert_offsets(src, out)
    assert hidden not in out
    assert Document.from_text(src, "latex").warnings == []


@pytest.mark.parametrize("src,kept", [
    ("We \\emph{zqword} it.", "zqword"),
    ("We \\textbf{zqword} it.", "zqword"),
    ("We \\textit{zqword} it.", "zqword"),
    ("We \\textbf{bold \\emph{zqword} claim} it.", "zqword"),
    ("Done.\\footnote{A zqword note.} Next.", "zqword"),
    ("Visit \\href{https://x.org}{our zqword page}.", "zqword"),
    ("The \\textcolor{red}{zqword} part.", "zqword"),
    ("The value was 5\\% higher.", "5\\%"),
    ("Two -- three.", "--"),
])
def test_text_arguments_stay_prose(src, kept):
    out = masked(src)
    assert_offsets(src, out)
    assert kept in out
    # ...and the macro names around them do not.
    assert "\\emph" not in out and "\\textbf" not in out


def test_macro_names_are_masked():
    out = masked("We \\noindent used \\LaTeX\\ and \\unknown{kept}.\\\\ End.")
    assert "\\" not in out and "noindent" not in out and "LaTeX" not in out
    assert "kept" in out and "End." in out


def test_preamble_and_trailer_are_masked():
    src = ("\\documentclass{article}\n\\usepackage{zqpkg}\n"
           "\\title{Zqtitle}\nzqloose words\n\\begin{document}\n"
           "Body text here.\n\\end{document}\nzqafter\n")
    out = masked(src)
    assert_offsets(src, out)
    assert "zq" not in out.lower()
    assert "Body text here." in out


def test_float_body_masked_except_caption():
    src = ("Before.\n\\begin{figure}[h]\n\\centering zqloose\n"
           "\\includegraphics{a.png}\n"
           "\\caption[Zqshort]{Weekly cases by \\emph{region}.}\n"
           "\\label{fig:cases}\n\\end{figure}\nAfter.")
    doc = Document.from_text(src, "latex")
    assert_offsets(src, doc.masked)
    assert "zqloose" not in doc.masked and "Zqshort" not in doc.masked
    assert "Weekly cases by" in doc.masked and "region" in doc.masked
    kinds = {s.kind: s for s in doc.structure}
    assert kinds["figure"].label == "fig:cases"
    assert kinds["caption"].label == "fig:cases"
    fig = kinds["figure"]
    assert src[fig.start:fig.end].startswith("\\begin{figure}")
    assert src[fig.start:fig.end].endswith("\\end{figure}")


def test_structure_items():
    src = ("\\begin{document}\nAs shown \\cite{k1,k2}.\n"
           "\\begin{equation}\\label{eq:r0} R = 2 \\end{equation}\n"
           "\\[ x = 1 \\]\nInline $y$ is not an equation item.\n"
           "\\begin{table}\\caption{Values.}\\label{tab:v}"
           "\\begin{tabular}{l}1\\end{tabular}\\end{table}\n"
           "\\end{document}\n")
    doc = Document.from_text(src, "latex")
    got = [(s.kind, s.label) for s in doc.structure if s.kind in PUBLIC]
    assert got == [("citation", "k1,k2"), ("equation", "eq:r0"),
                   ("equation", None), ("table", "tab:v"),
                   ("caption", "tab:v")]


def test_subfigure_labels_name_their_own_captions():
    src = ("\\begin{figure}\\begin{subfigure}{0.5\\textwidth}"
           "\\caption{Left.}\\label{fig:a}\\end{subfigure}"
           "\\caption{Both panels.}\\label{fig:both}\\end{figure}")
    got = [(s.kind, s.label)
           for s in Document.from_text(src, "latex").structure
           if s.kind in PUBLIC]
    assert got == [("figure", "fig:both"), ("caption", "fig:a"),
                   ("caption", "fig:both")]


def test_label_inside_center_still_names_the_figure():
    src = ("\\begin{figure}\\begin{center}\\includegraphics{a}"
           "\\caption{Cases.}\\label{fig:c}\\end{center}\\end{figure}")
    got = [(s.kind, s.label)
           for s in Document.from_text(src, "latex").structure
           if s.kind in PUBLIC]
    assert got == [("figure", "fig:c"), ("caption", "fig:c")]


PUBLIC = {"figure", "table", "equation", "caption", "citation"}


def test_labels_and_refs_are_recorded_for_the_structural_checks():
    src = ("\\begin{document}\\section{A}\\label{sec:a}\n"
           "See \\cref{fig:x,tab:y} and Section~\\ref{sec:a}.\n"
           "\\end{document}\n")
    items = Document.from_text(src, "latex").structure
    assert [s.label for s in items if s.kind == "ref"] == [
        "fig:x", "tab:y", "sec:a"]
    assert [s.label for s in items if s.kind == "label"] == ["sec:a"]


def test_every_mask_whole_macro_has_an_argument_spec():
    """A name in MASK_WHOLE without a spec masks nothing: pylatexenc
    leaves its `{...}` as ordinary groups, which are kept as prose."""
    from researchly.ingest.latex import MASK_WHOLE, _context
    db = _context()
    no_args = {"footnotemark", "printbibliography"}   # only `[...]` options
    missing = [m for m in sorted(MASK_WHOLE - no_args)
               if "{" not in db.get_macro_spec(m).args_parser.argspec]
    assert missing == []


@pytest.mark.parametrize("src,hidden", [
    ("\\addtolength{\\textwidth}{2zqcm} Body.", "zqcm"),
    ("\\email{zq@host.org} Body.", "zq@"),
    ("\\iffalse Zqold draft text {\n\\fi Body.", "Zqold"),
    ("\\def\\zqmacro#1{\\begin{quote}#1} Body.", "zqmacro"),
    ("\\begin{multicols}{2}Body.\\end{multicols}", "2"),
    ("\\begin{minipage}[t]{0.5zqwidth}Body.\\end{minipage}", "zqwidth"),
])
def test_more_non_prose_arguments(src, hidden):
    doc = Document.from_text(src, "latex")
    assert doc.warnings == []
    assert hidden not in doc.masked and "Body." in doc.masked


def test_definitions_do_not_force_the_fallback():
    """Definitions hold unmatched \\begin/\\end and are read raw, in the
    preamble (not parsed at all) and in the body."""
    pre = ("\\documentclass{article}\n"
           "\\newenvironment{myq}{\\begin{quote}}{\\end{quote}}\n"
           "\\iffalse { \\fi\n\\begin{document}\n")
    body = ("\\renewcommand{\\zqcmd}[1]{\\begin{center}#1}\n"
            "Body text here.\n\\end{document}\nAfter the end { $ unclosed\n")
    doc = Document.from_text(pre + body, "latex")
    assert doc.warnings == []
    assert doc.masked.split() == ["Body", "text", "here."]


def test_part_and_subparagraph_are_headings():
    doc = Document.from_text("\\part{Background}\nText.\n"
                             "\\subparagraph{Results.} More text.\n", "latex")
    assert [(h.text, h.section) for h in doc.headings] == [
        ("Background", "introduction"), ("Results.", "results")]
    assert "More text." in doc.masked and "Background" not in doc.masked


# --- headings ---------------------------------------------------------------

def test_headings_and_sections():
    src = ("\\section{Introduction}\nText.\n\\section*{Materials and methods}"
           "\nText.\n\\section[Short]{Main \\emph{results}}\nText.\n"
           "\\subsubsection{Discussion}\nText.\n")
    doc = Document.from_text(src, "latex")
    assert [(h.text, h.section) for h in doc.headings] == [
        ("Introduction", "introduction"), ("Materials and methods", "methods"),
        ("Main results", "results"), ("Discussion", "discussion")]
    assert "Introduction" not in doc.masked     # headings are not sentences


def test_paragraph_heading_does_not_mask_the_rest_of_its_line():
    src = "\\paragraph{Estimation.} We fitted the model to weekly counts.\n"
    doc = Document.from_text(src, "latex")
    assert doc.headings[0].section == "methods"
    assert "We fitted the model to weekly counts." in doc.masked
    assert "Estimation" not in doc.masked


def test_abstract_environment_is_a_section():
    doc = Document.from_text(
        "\\begin{abstract}\nWe report a result.\n\\end{abstract}\n", "latex")
    assert [h.section for h in doc.headings] == ["abstract"]


# --- parity with the regex masker -------------------------------------------

PARITY = [
    "There are \\cite{jones} studies that report this.",
    "\\section{Methods}\nSamples were incubated at 37 degrees "
    "\\cite{smith2020}.\n\\section{Results}\nThe effect was significant.\n",
    # (\\texttt is code since P28, so it is no longer a parity case: see
    # tests/test_real_document_precision.py.)
    "We used \\textit{R} and \\textbf{Stan}~\\citep{a}. See Fig.~\\ref{f}.",
    "\\begin{itemize}\n\\item One thing.\n\\item Another thing.\n"
    "\\end{itemize}",
    "\\begin{align}\na &= b \\\\\nc &= d\n\\end{align}\nAfter.",
    "The value was 5\\% and R\\&D grew. New line \\noindent here.",
]


@pytest.mark.parametrize("src", PARITY)
def test_same_words_as_regex_masker(src):
    """Outside headings (masked by from_text either way) the parser keeps
    the same words the regex masker kept on ordinary input."""
    new = Document.from_text(src, "latex")
    old_masked, old_headings = _mask_latex(src)
    assert [h.section for h in new.headings] == \
        [h.section for h in old_headings]
    old = list(old_masked)
    for h in old_headings:            # what from_text did to regex output
        end = old_masked.find("\n", h.start)
        old[h.start:end] = " " * (end - h.start)
    assert new.masked.split() == "".join(old).split()


def test_unparseable_input_falls_back_with_warning():
    src = "Line one.\nA stray} brace and \\emph{x}.\n"
    doc = Document.from_text(src, "latex")
    assert len(doc.masked) == len(src)
    assert "Line one." in doc.masked and "\\emph" not in doc.masked
    assert len(doc.warnings) == 1
    assert "near line 2" in doc.warnings[0]
    assert "unbalanced" in doc.warnings[0]
    assert "brace and" not in doc.warnings[0]    # never quotes the text


def test_unclosed_construct_warns_without_a_misleading_position():
    # The parser only learns at the end of the file that `$` never closed.
    doc = Document.from_text("Line one.\nCosts $5 here.\n\nMore.\n", "latex")
    assert len(doc.warnings) == 1 and "near" not in doc.warnings[0]


def test_fallback_matches_regex_masker():
    src = "An {unbalanced \\cite{k} brace.\n"
    res = mask_latex(src)
    assert res.masked == _mask_latex(src)[0]
    assert res.warnings


def test_missing_parser_falls_back_and_says_so(monkeypatch):
    """A Mac that has not re-run `pip install -r requirements.txt` still
    checks LaTeX, and is told why markup may slip through."""
    import sys
    monkeypatch.setitem(sys.modules, "pylatexenc", None)
    src = "We \\emph{did} it \\cite{k}.\n"
    res = mask_latex(src)
    assert res.masked == _mask_latex(src)[0]
    assert "pylatexenc" in res.warnings[0]


def test_deep_nesting_falls_back_instead_of_crashing():
    src = "{" * 5000 + "x" + "}" * 5000
    doc = Document.from_text(src, "latex")
    assert len(doc.masked) == len(src)
    assert doc.warnings


# --- seeded random round trip ------------------------------------------------

# "<i>" is replaced by the fragment's index so labels and keys differ.
FRAGMENTS = [
    "We fitted a model. ", "\\emph{weekly} ", "\\cite{k<i>} ", "$x_<i>$ ",
    "\\section{Results}\n", "\\paragraph{Fit.} ", "% note <i> {\n",
    "\\begin{equation}a=<i>\\label{eq:<i>}\\end{equation}\n",
    "\\footnote{A note <i>.} ", "\\begin{figure}\\caption{Cap <i>.}"
    "\\label{fig:<i>}\\end{figure}\n", "\\url{http://h/<i>%20} ",
    "\\begin{itemize}\\item One. \\item[b] Two.\\end{itemize}\n",
    "\\\\ ", "--- ", "\\textbf{bold \\emph{n<i>}} ", "\n\n", "5\\% ",
    "\\begin{verbatim}\n$ % {\n\\end{verbatim}\n", "\\ref{s<i>}. ",
    "\\href{http://h/<i>}{link <i>} ", "\\[ y = <i> \\]\n",
]


@pytest.mark.parametrize("seed", range(40))
def test_random_documents_keep_offsets(seed):
    rng = random.Random(seed)
    body = "".join(rng.choice(FRAGMENTS).replace("<i>", str(i))
                   for i in range(rng.randint(1, 40)))
    src = ("\\documentclass{article}\n\\begin{document}\n" + body
           + "\n\\end{document}\n") if seed % 2 else body
    doc = Document.from_text(src, "latex")
    assert doc.warnings == []
    assert_offsets(src, doc.masked)
    for item in doc.structure:
        assert 0 <= item.start < item.end <= len(src)
    assert "\\cite" not in doc.masked and "\\emph" not in doc.masked
    single = load_bytes("chapter.tex", src.encode("utf-8"))
    assert single.segments[0].end == len(src) == len(single.masked)


# --- section-awareness and rules survive ingest ------------------------------

def test_methods_passive_not_flagged_but_results_is():
    agent = "The pattern was first described by Anderson and May."
    methods = f"\\section{{Methods}}\n{agent}\n"
    results = f"\\section{{Results}}\n{agent}\n"
    assert not flagged(methods, "G104")
    assert flagged(results, "G104")


def test_spelling_error_in_caption_is_checked():
    src = ("\\begin{figure}\\includegraphics{a.png}"
           "\\caption{Weekly incidense by region.}\\end{figure}\n")
    hits = flagged(src, "S001", disabled={"LT001"})
    assert [src[s.start:s.end] for s in hits] == ["incidense"]


def test_equation_and_cite_key_not_spellchecked():
    src = ("We used the estimate \\cite{wrongspeling2020} and "
           "$\\mathrm{qwertyzz}$ here.\n"
           "\\begin{equation}\\text{mispeled} = 1\\end{equation}\n")
    hits = flagged(src, "S001", disabled={"LT001"})
    assert hits == []
