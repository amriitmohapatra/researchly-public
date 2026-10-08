"""Overleaf project .zip ingest (researchly.ingest.latex_project).

Fixtures are synthetic projects built in memory. Hostile cases assert the
error code and that the message quotes neither document text nor the
uploaded filename.
"""

import random
import zipfile

import pytest

from researchly import api, cli
from researchly.engine import check
from researchly.ingest import IngestError, load_bytes, source_position
from researchly.ingest import _zip
from ingest_fixtures import set_encrypted_flag, zip_bytes

NLP = api.get_nlp()
SECRET = "Zqsecret"           # appears in fixture text, never in messages
NAME = "zq-private-chapter.zip"

MAIN = ("\\documentclass{report}\n\\begin{document}\n"
        "\\chapter{Introduction}\nWe study weekly counts.\n"
        "% \\input{old-draft}\n"
        "\\input{chapters/methods}\n"
        "\\include{chapters/results}\n"
        "Closing words here.\n\\end{document}\n")
METHODS = ("\\section{Methods}\n"
           "The pattern was first described by Anderson and May.\n"
           "\\input{tables}\n")          # relative to the including file
TABLES = "Table text with a mispeled word.\n"
RESULTS = ("\\section{Results}\n"
           "The pattern was first described by Anderson and May.\n")
PROJECT = {"main.tex": MAIN, "chapters/methods.tex": METHODS,
           "chapters/tables.tex": TABLES, "chapters/results.tex": RESULTS,
           "refs.bib": "@article{k, title={Zqsecret}}",
           "figs/plot.png": b"\x89PNG\r\n",
           "inner.zip": zip_bytes({"evil.tex": "\\documentclass{x}"})}


def load(files, name=NAME):
    return load_bytes(name, zip_bytes(files))


def assert_round_trip(doc, files):
    """Every segment is a verbatim slice of its source file, and the
    segments tile the combined text."""
    assert len(doc.masked) == len(doc.original)
    pos = 0
    for seg in doc.segments:
        assert seg.start == pos and seg.end > seg.start
        src = files[seg.path]
        n = seg.end - seg.start
        assert doc.original[seg.start:seg.end] == \
            src[seg.source_start:seg.source_start + n]
        pos = seg.end
    assert pos == len(doc.original)


def rejected(data, code, name=NAME):
    with pytest.raises(IngestError) as e:
        load_bytes(name, data)
    assert e.value.code == code
    assert SECRET.lower() not in e.value.message.lower()
    assert name not in e.value.message and "zq-private" not in e.value.message
    return e.value


# --- expansion ---------------------------------------------------------------

def test_inputs_expand_in_reading_order():
    doc = load(PROJECT)
    assert_round_trip(doc, PROJECT)
    assert [s.path for s in doc.segments] == [
        "main.tex", "chapters/methods.tex", "chapters/tables.tex",
        "chapters/methods.tex", "main.tex", "chapters/results.tex",
        "main.tex"]
    order = [doc.original.find(t) for t in
             ("We study", "\\section{Methods}", "Table text", "Results",
              "Closing words")]
    assert order == sorted(order) and -1 not in order
    # the command stays in the parent's segment, and is masked
    first = doc.segments[0]
    assert doc.original[first.start:first.end].endswith(
        "\\input{chapters/methods}")
    assert "chapters/methods" not in doc.masked
    assert "old-draft" not in doc.masked       # commented-out input ignored
    assert doc.warnings == []
    assert doc.path == NAME
    assert [h.section for h in doc.headings] == [
        "introduction", "methods", "results"]


def test_source_position_points_into_the_child_file():
    doc = load(PROJECT)
    at = doc.original.find("mispeled")
    assert source_position(doc.segments, doc.original, at) == \
        ("chapters/tables.tex", 1, TABLES.find("mispeled") + 1)
    at = doc.original.find("Closing words")
    assert source_position(doc.segments, doc.original, at) == \
        ("main.tex", 8, 1)


def test_section_awareness_and_spelling_survive_the_project():
    doc = load(PROJECT)
    out = check(doc, NLP, show_preferences=True, disabled={"LT001"})
    g104 = [s for s in out if s.rule_id == "G104"]
    assert [s.section for s in g104] == ["results"]   # Methods stays quiet
    spelled = [doc.original[s.start:s.end] for s in out if s.rule_id == "S001"]
    assert spelled == ["mispeled"]


def test_missing_cycle_and_depth_skip_with_warnings():
    files = {"main.tex": "\\documentclass{article}\n\\begin{document}\n"
                         "A.\\input{nope}\n\\input{a}\n\\input{d0}\n"
                         "\\end{document}\n",
             "a.tex": "In a.\\input{b}\n",
             "b.tex": "In b.\\input{a}\n"}
    for i in range(12):
        files[f"d{i}.tex"] = f"Level {i}.\\input{{d{i + 1}}}\n"
    doc = load(files)
    assert_round_trip(doc, files)
    w = " ".join(doc.warnings)
    assert "\\input{nope} was not found" in w
    assert "cycle" in w and "nested more than 10" in w
    assert "Level 9." in doc.original and "Level 11." not in doc.original
    assert all(len(x) < 200 for x in doc.warnings)


def test_main_file_detection():
    sub = "\\documentclass[../main.tex]{subfiles}\n\\begin{document}x\n" \
          "\\end{document}\n"
    root = "\\documentclass{article}\n\\begin{document}Hi.\\end{document}\n"
    # subfiles chapters do not count as main files
    assert load({"thesis.tex": root, "ch/one.tex": sub}).segments[0].path \
        == "thesis.tex"
    # several real roots: main.tex wins
    assert load({"main.tex": root, "other.tex": root}).segments[0].path \
        == "main.tex"
    # no \documentclass anywhere: the only .tex
    assert load({"notes.tex": "Just text.\n"}).segments[0].path == "notes.tex"
    # a project folder inside the zip resolves inputs from its own root
    doc = load({"Proj/main.tex": root.replace("Hi.", "\\input{s}"),
                "Proj/s.tex": "Inside."})
    assert "Inside." in doc.original
    # two indistinguishable roots: one is chosen (deterministically) and the
    # user is told which, rather than the project being refused (P29)
    tie = load({"a.tex": root, "b.tex": root})
    assert tie.segments[0].path in ("a.tex", "b.tex")
    assert any("several main .tex files" in w for w in tie.warnings)
    rejected(zip_bytes({"a.tex": "x", "b.tex": "y"}), "unreadable_file")
    rejected(zip_bytes({"readme.md": SECRET}), "unreadable_file")


@pytest.mark.parametrize("seed", range(15))
def test_random_projects_round_trip(seed):
    rng = random.Random(seed)
    names = [f"part{i}.tex" for i in range(rng.randint(1, 6))]
    files = {}
    for i, name in enumerate(names):
        body = []
        for j in range(rng.randint(0, 8)):
            pick = rng.random()
            if pick < 0.3 and i + 1 < len(names):
                target = rng.choice(names[i + 1:])[:-4]
                body.append(f"\\{rng.choice(['input', 'include'])}"
                            f"{{{target}}}")
            elif pick < 0.4:
                body.append(f"$x_{j}$ and \\cite{{k{j}}}")
            else:
                body.append(f"Sentence {j} of part {i}.\n")
        files[name] = "".join(body)
    files["main.tex"] = ("\\documentclass{article}\n\\begin{document}\n"
                         "\\input{part0}\n\\end{document}\n")
    doc = load(files)
    assert_round_trip(doc, files)


# --- hostile inputs ------------------------------------------------------------

def test_not_a_zip():
    e = rejected(b"PK\x03\x04 " + SECRET.encode() * 10, "unreadable_file")
    assert "could not be opened" in e.message
    rejected(SECRET.encode(), "unreadable_file")


@pytest.mark.parametrize("bad", ["../evil.tex", "/etc/evil.tex",
                                 "C:/evil.tex", "ok/../../evil.tex",
                                 "..\\evil.tex"])
def test_path_traversal_rejected(bad):
    rejected(zip_bytes({"main.tex": "\\documentclass{a}" + SECRET,
                        bad: SECRET}), "unreadable_file")


def test_symlink_member_rejected():
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.tex", "\\documentclass{a}" + SECRET)
        link = zipfile.ZipInfo("chapter.tex")
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        zf.writestr(link, "/etc/passwd")
    rejected(buf.getvalue(), "unreadable_file")


def test_too_many_entries():
    files = {f"f{i}.tex": SECRET for i in range(_zip.MAX_ENTRIES + 1)}
    rejected(zip_bytes(files), "payload_too_large")


def test_zip_bomb_member_ratio():
    rejected(zip_bytes({"main.tex": "\\documentclass{a}",
                        "bomb.tex": b"\0" * (2 * 1024 * 1024)}),
             "payload_too_large")


def test_total_uncompressed_limit():
    big = b"\0" * (26 * 1024 * 1024)        # stored: ratio 1, total 52 MB
    rejected(zip_bytes({"a.bin": big, "b.bin": big},
                       compression=zipfile.ZIP_STORED), "payload_too_large")


def test_include_fan_out_cannot_build_a_huge_text():
    files = {"main.tex": "\\documentclass{a}" + "\\input{l0}" * 10}
    for i in range(6):
        files[f"l{i}.tex"] = f"\\input{{l{i + 1}}}" * 10
    files["l6.tex"] = SECRET * 20
    rejected(zip_bytes(files), "payload_too_large")


def test_encrypted_member_rejected():
    data = set_encrypted_flag(zip_bytes({"main.tex": "\\documentclass{a}"
                                         + SECRET}))
    e = rejected(data, "unreadable_file")
    assert "password" in e.message


LATIN1 = "\\documentclass{a}\nCaf\xe9 ".encode("latin-1") + SECRET.encode()


def test_non_utf8_main_tex_rejected():
    rejected(zip_bytes({"main.tex": LATIN1}), "unreadable_file")
    rejected(zip_bytes({"main.tex": LATIN1, "x.tex": "Text."}),
             "unreadable_file")


def test_non_utf8_input_is_skipped_and_an_unused_one_ignored():
    files = {"main.tex": "\\documentclass{a}\\begin{document}Hi."
                         "\\input{old}\\end{document}",
             "old.tex": "Caf\xe9".encode("latin-1"),
             "unused/template.tex": LATIN1}
    doc = load(files)
    assert doc.warnings == ["\\input{old} is not UTF-8 text; skipped. Save "
                            "it as UTF-8 to have it checked."]
    del files["main.tex"]
    files["main.tex"] = "\\documentclass{a}\\begin{document}Hi.\\end{document}"
    assert load(files).warnings == []


def test_nested_zip_and_other_files_ignored():
    doc = load(PROJECT)
    assert "evil" not in doc.original and SECRET not in doc.original


# --- CLI -------------------------------------------------------------------------

def test_cli_checks_a_zip_and_reports_bad_ones(tmp_path, capsys):
    good = tmp_path / "project.zip"
    good.write_bytes(zip_bytes(PROJECT))
    assert cli.main(["check", str(good), "--no-metrics"]) == 1
    out = capsys.readouterr().out
    assert "chapters/tables.tex:1:" in out          # file:line:col locations
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"not a zip")
    assert cli.main(["check", str(bad)]) == 2
    assert "could not be opened" in capsys.readouterr().err


def test_cli_json_keeps_going_and_maps_sources(tmp_path, capsys):
    import json
    good = tmp_path / "project.zip"
    good.write_bytes(zip_bytes(PROJECT))
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"not a zip")
    assert cli.main(["check", str(bad), str(good), "--json",
                     "--no-metrics"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert [p["file"] for p in payload] == [str(good)]
    sources = {(s["source"]["path"], s["text"])
               for s in payload[0]["suggestions"]}
    assert ("chapters/tables.tex", "mispeled") in sources


# --- P29 real-document bench: several \documentclass files ---------------------

DOC = "\\documentclass{article}\n\\begin{document}\n{body}\n\\end{document}\n"


def test_cover_letter_beside_the_manuscript_is_not_the_main_file():
    files = {"manuscript.tex": DOC.replace("{body}", "The model was fitted.\n\\input{methods}"),
             "methods.tex": "Counts were weekly.\n",
             "cover_letter.tex": DOC.replace("{body}", "Dear Editor, please consider it.")}
    doc = load_bytes("p.zip", zip_bytes(files))
    assert "The model was fitted." in doc.original
    assert "Dear Editor" not in doc.original
    assert any("checked manuscript.tex" in w for w in doc.warnings)


def test_two_versions_prefer_the_one_that_includes_more():
    files = {"paper.tex": DOC.replace("{body}", "Short version."),
             "paper_journal.tex": DOC.replace("{body}", "Long version.\n\\input{a}\n\\input{b}"),
             "a.tex": "Part A.\n", "b.tex": "Part B.\n"}
    doc = load_bytes("p.zip", zip_bytes(files))
    assert "Long version." in doc.original and "Part B." in doc.original
    assert any("paper_journal.tex" in w and "paper.tex" in w for w in doc.warnings)
