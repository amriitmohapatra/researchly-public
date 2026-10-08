"""The demo manuscript: every planted error fires, nothing else does, and
the three formats say the same thing.

    cd <repo> && python3.10 -m pytest demo/tests -q

The artefacts are rebuilt into a temporary directory from demo/manuscript.py
(the committed demo/dist/ is the same build), then read through the same
path the website uses (`ingest.load_bytes` -> `api.analyze`).
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "core"))
sys.path.insert(0, str(REPO / "demo"))

import build_demo  # noqa: E402
import manuscript as ms  # noqa: E402
from researchly import api  # noqa: E402
from researchly.ingest import load_bytes  # noqa: E402

# Flags per 1,000 words allowed beyond the planted ones. The demo is meant
# to show precision: tune the prose, never the engine.
NOISE_PER_1000_WORDS = 12

# (rule, section, text the flag must sit on or name) for each planted
# error. `formats` says where the error can be seen at all: the Markdown
# version has no figures, tables or equation objects, so the structural
# rules cannot apply to it. Text patterns are matched against the flagged
# span OR the message, because a structural rule anchors on a nearby word.
PLANTED = [
    ("AB802", "abstract", r"significance", ("docx", "zip", "md")),
    ("E704", "introduction", r"is known to", ("docx", "zip", "md")),
    ("LT001", "introduction", r"\ban\b", ("docx", "zip", "md")),
    ("W207", "methods", r"the the", ("docx", "zip", "md")),
    ("F612", "methods", r"EIP", ("docx", "zip", "md")),
    ("X302", "methods", r"full stop", ("docx", "zip")),
    ("S001", "methods", r"seperate", ("docx", "zip", "md")),
    ("X102", "results", r"Figure 1 is first cited after Figure 2",
     ("docx", "zip")),
    ("E707", "results", r"Figure 1 shows", ("docx", "zip", "md")),
    ("X401", "results", r"4\.8", ("docx", "zip")),
    ("S001", "results", r"transmision", ("docx", "zip", "md")),
    ("X202", "results", r"Weekly reported dengue cases", ("docx", "zip")),
    ("X101", "results", r"Table 2 is never cited", ("docx", "zip")),
    ("G104", "discussion", r"was shown by Lim", ("docx", "zip", "md")),
    ("C302", "discussion", r"proves", ("docx", "zip", "md")),
    ("X103", "discussion", r"Figure 3|fig:missing", ("docx", "zip")),
    ("C301", "discussion", r"may possibly", ("docx", "zip", "md")),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    return build_demo.build_all(out)


@pytest.fixture(scope="module")
def analyses(built):
    nlp = api.get_nlp()
    out = {}
    for kind, path in built.items():
        doc = load_bytes(path.name, path.read_bytes())
        out[kind] = (doc, api.analyze(doc, nlp=nlp, show_preferences=True))
    return out


def _flags(doc, analysis):
    return [(s.rule_id, doc.section_at(s.start),
             doc.original[s.start:s.end], s.message, s)
            for s in analysis.suggestions]


def _matches(flag, rule, section, pattern):
    rid, sec, text, message, _ = flag
    return (rid == rule and sec == section
            and (re.search(pattern, text) or re.search(pattern, message)))


@pytest.mark.parametrize("rule,section,pattern,formats",
                         PLANTED, ids=[f"{p[0]}-{p[1]}" for p in PLANTED])
def test_planted_error_fires(analyses, rule, section, pattern, formats):
    for kind in formats:
        doc, analysis = analyses[kind]
        if rule == "LT001" and not analysis.grammar_ok:
            pytest.skip("grammar tier (LanguageTool) not available here")
        hits = [f for f in _flags(doc, analysis)
                if _matches(f, rule, section, pattern)]
        assert len(hits) == 1, (
            f"{rule} in {section} ({pattern!r}) fired {len(hits)} times in "
            f"the {kind}: {[h[:4] for h in _flags(doc, analysis) if h[0] == rule]}")


@pytest.mark.parametrize("kind", ["docx", "zip", "md"])
def test_noise_is_low(analyses, kind):
    doc, analysis = analyses[kind]
    planted = [p for p in PLANTED if kind in p[3]
               and not (p[0] == "LT001" and not analysis.grammar_ok)]
    flags = _flags(doc, analysis)
    extra = [f[:4] for f in flags
             if not any(_matches(f, r, s, pat) for r, s, pat, _ in planted)]
    words = len(re.findall(r"[A-Za-z]+", doc.masked))
    allowed = NOISE_PER_1000_WORDS * words / 1000
    assert len(extra) <= allowed, (
        f"{len(extra)} unplanted flags in the {kind} "
        f"(allowed {allowed:.0f} for {words} words): {extra}")
    # The demo is tuned to zero noise; report any drift loudly.
    assert len(flags) == len(planted) + len(extra)


def test_prose_length():
    prose = [build_demo.render_plain(b.text)
             for b in ms.ABSTRACT + ms.BODY if isinstance(b, ms.P)]
    words = sum(len(re.findall(r"[A-Za-z]+", p)) for p in prose)
    assert 1400 <= words <= 1900, words


def test_formats_carry_the_same_prose(built):
    import docx
    prose = [build_demo.render_plain(b.text)
             for b in ms.ABSTRACT + ms.BODY if isinstance(b, ms.P)]
    word_paras = {p.text for p in docx.Document(str(built["docx"])).paragraphs}
    md_lines = set(built["md"].read_text(encoding="utf-8").split("\n"))
    for para in prose:
        assert para in word_paras, para[:60]
        assert para in md_lines, para[:60]
    # The LaTeX version: every source paragraph, rendered with its own
    # markup (\cite, \ref, $maths$), appears verbatim in the project.
    with zipfile.ZipFile(built["zip"]) as zf:
        tex = "\n".join(zf.read(n).decode("utf-8") for n in zf.namelist()
                        if n.endswith(".tex"))
    for block in ms.ABSTRACT + ms.BODY:
        if isinstance(block, ms.P):
            assert build_demo.render_tex(block.text) in tex, block.text[:60]


def test_overleaf_project_shape(built):
    with zipfile.ZipFile(built["zip"]) as zf:
        names = set(zf.namelist())
        main = zf.read("main.tex").decode("utf-8")
        sections = {n: zf.read(n).decode("utf-8") for n in names
                    if n.startswith("sections/")}
    assert {"main.tex", "references.bib", "figures/fig1_weekly_cases.png",
            "figures/fig2_model_fit.png"} <= names
    assert len(sections) == 5
    for n in sections:
        assert f"\\input{{{n[:-4]}}}" in main
    body = "\n".join(sections.values())
    assert body.count(r"\begin{equation}") == 2
    assert body.count(r"\begin{figure}") == 2
    assert body.count(r"\begin{table}") == 2
    assert r"\ref{fig:missing}" in body
    assert "\\citep{" in body and "\\citet{" in body
    for env in ("equation", "figure", "table", "tabular"):
        assert body.count(f"\\begin{{{env}}}") == body.count(f"\\end{{{env}}}")


def test_word_file_shape(built):
    import docx
    d = docx.Document(str(built["docx"]))
    styles = [p.style.name for p in d.paragraphs]
    assert styles.count("Heading 1") == 7            # Abstract .. References
    assert styles.count("Heading 2") == 3
    assert styles.count("Caption") == 4
    assert len(d.tables) == 2 and len(d.inline_shapes) == 2
    assert sum("oMathPara" in p._p.xml for p in d.paragraphs) == 2


def test_figures_are_small(built):
    for png in (built["docx"].parent / "figures").glob("*.png"):
        assert png.stat().st_size < 60_000, png
