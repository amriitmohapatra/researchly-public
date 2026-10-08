"""Word .docx ingest (researchly.ingest.docx).

Documents are hand-written minimal OOXML (tests/ingest_fixtures.py) with
synthetic sentences. Hostile cases assert the error code and that the
message quotes neither document text nor the uploaded filename.
"""

import random

import pytest

from researchly import api, cli
from researchly.document import Document
from researchly.engine import check
from researchly.ingest import IngestError, load_bytes
from ingest_fixtures import (STYLES, deleted, docx_bytes, drawing, equation,
                             field, inserted, para, run, set_encrypted_flag,
                             table, zip_bytes)

NLP = api.get_nlp()
SECRET = "Zqsecret"
NAME = "zq-private-chapter.docx"
AGENT = "The pattern was first described by Anderson and May."


def load(body, **kw):
    return load_bytes(NAME, docx_bytes(body, **kw))


def rules(doc, rule_id):
    return [s for s in check(doc, NLP, show_preferences=True,
                             disabled={"LT001"}) if s.rule_id == rule_id]


def rejected(data, code):
    with pytest.raises(IngestError) as e:
        load_bytes(NAME, data)
    assert e.value.code == code
    assert SECRET.lower() not in e.value.message.lower()
    assert NAME not in e.value.message and "zq-private" not in e.value.message
    return e.value


# --- text ------------------------------------------------------------------------

def test_runs_tabs_breaks_and_paragraphs():
    doc = load(para("One ", "two", "<w:r><w:tab/><w:t>three</w:t><w:br/>"
                    "<w:t>four</w:t></w:r>") + para("Next paragraph."))
    assert doc.original == "One two\tthree\nfour\n\nNext paragraph."
    assert doc.kind == "word" and doc.path == NAME
    assert len(doc.segments) == 1 and doc.segments[0].end == len(doc.original)


def test_tracked_changes_read_as_accepted():
    doc = load(para("We ", deleted("Zqgone mispeled "), inserted("now "),
                    "estimate it."))
    assert doc.original == "We now estimate it."
    assert rules(doc, "S001") == []


def test_field_codes_dropped_results_kept():
    code = ' ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"qwrtzxv"} '
    doc = load(para("Shown before ", field(code, "(Smith 2020)"), "."))
    assert doc.original == "Shown before (Smith 2020)."
    assert "qwrtzxv" not in doc.original and rules(doc, "S001") == []


def test_hidden_text_dropped():
    doc = load(para("Visible ", run("Zqhidden", hidden=True), "text."))
    assert doc.original == "Visible text."


def test_equation_masked_and_recorded():
    doc = load(para("The rate ", equation("qzxvbn"), " was stable."))
    assert "qzxvbn" not in doc.original
    eq = [s for s in doc.structure if s.kind == "equation"]
    assert len(eq) == 1
    assert doc.original[eq[0].start:eq[0].end] == "[equation]"
    assert doc.masked[eq[0].start:eq[0].end].strip() == ""
    assert len(doc.masked) == len(doc.original)
    assert rules(doc, "S001") == []


def test_displayed_equation_after_a_full_stop_is_flagged():
    # the equation object alone in its paragraph, numbered: displayed
    doc = load(para("We assume mass action.")
               + para(equation("qzxvbn"), "\t(1)")
               + para("where N is the population."))
    (h,) = rules(doc, "X302")
    assert doc.original[h.start:h.end] == "action."
    # led in, and an equation inside a sentence: quiet
    assert rules(load(para("The rate is") + para(equation("qzxvbn"))
                      + para("where N is the population.")), "X302") == []
    assert rules(load(para("We assume mass action.")
                      + para("Here ", equation("qzxvbn"), " holds.")),
                 "X302") == []


def test_drawing_caption_and_table_structure():
    doc = load(para(drawing()) +
               para("Weekly incidense by region.", style="Beschriftung") +
               table([["Methods", "0.3"], ["Rate", "Zqcell"]]) +
               para("After the table."))
    kinds = [s.kind for s in doc.structure]
    assert kinds == ["figure", "caption", "table"]
    assert "boxtext" not in doc.original           # text boxes ignored in S2
    tbl = doc.structure[2]
    assert doc.original[tbl.start:tbl.end].startswith("Methods")
    assert doc.original[tbl.start:tbl.end].endswith("Zqcell")
    # a cell reading "Methods" is not a heading
    assert doc.headings == []
    assert doc.in_table(doc.original.find("Zqcell"))
    # a typo in a caption is checked
    spelled = [doc.original[s.start:s.end] for s in rules(doc, "S001")]
    assert "incidense" in spelled


# --- headings and section-awareness -------------------------------------------

def test_localised_and_custom_heading_styles():
    doc = load(para("Methods", style="berschrift1") +       # id localised
               para("Body.") +
               para("Results", style="Kapitel") +           # basedOn heading
               para("Body.") +
               para("Discussion", outline=1) +              # direct outline
               para("Body.") +
               para("My title", style="Titel"))
    assert [(h.text, h.section) for h in doc.headings] == [
        ("Methods", "methods"), ("Results", "results"),
        ("Discussion", "discussion"), ("My title", "front")]   # a title is no section (P37)


def test_matches_the_word_addin_path():
    body = (para("Methods", style="berschrift1") + para(AGENT) +
            para("Results", style="berschrift1") + para(AGENT))
    doc = load(body)
    addin = Document.from_word([
        {"text": "Methods", "style": "heading 1"}, {"text": AGENT},
        {"text": "Results", "style": "heading 1"}, {"text": AGENT}])
    assert doc.original == addin.original and doc.masked == addin.masked
    g104 = rules(doc, "G104")
    assert [s.section for s in g104] == ["results"]   # Methods stays quiet


def test_without_styles_part_still_reads():
    doc = load(para("Methods", style="Heading1") + para(AGENT), styles=None)
    assert doc.original.startswith("Methods")


@pytest.mark.parametrize("seed", range(20))
def test_random_documents_round_trip(seed):
    rng = random.Random(seed)
    body, expected = [], []
    for i in range(rng.randint(1, 25)):
        pick = rng.random()
        words = f"Sentence {i} reads well."
        if pick < 0.2:
            body.append(para(f"Heading {i}", style="berschrift1"))
            expected.append(f"Heading {i}")
        elif pick < 0.35:
            body.append(para("Kept ", deleted("gone "), inserted("new "),
                             words))
            expected.append("Kept new " + words)
        elif pick < 0.5:
            body.append(para("See ", field("REF x \\h", "Table 1"), "."))
            expected.append("See Table 1.")
        elif pick < 0.6:
            body.append(para("A ", equation("x+y"), " B."))
            expected.append("A [equation] B.")
        elif pick < 0.7:
            body.append(table([[f"c{i}", "d"], ["e", "f"]]))
            expected += [f"c{i}", "d", "e", "f"]
        else:
            body.append(para(words))
            expected.append(words)
    doc = load("".join(body))
    source = "\n\n".join(expected)
    assert doc.original == source
    assert len(doc.masked) == len(doc.original)
    seg = doc.segments[0]
    assert (seg.path, seg.start, seg.end, seg.source_start) == \
        (NAME, 0, len(source), 0)
    for item in doc.structure:
        assert 0 <= item.start <= item.end <= len(source)


# --- hostile inputs ------------------------------------------------------------

def test_xxe_rejected():
    prolog = ('<!DOCTYPE w:document [<!ENTITY xxe SYSTEM '
              '"file:///etc/passwd">]>')
    data = docx_bytes(f"<w:p><w:r><w:t>{SECRET} &xxe;</w:t></w:r></w:p>",
                      prolog=prolog)
    rejected(data, "unreadable_file")


def test_billion_laughs_rejected():
    ents = '<!ENTITY a "Zqsecret">' + "".join(
        f'<!ENTITY {c} "&{p};&{p};&{p};&{p};&{p};&{p};&{p};&{p};&{p};&{p};">'
        for p, c in zip("abcdefgh", "bcdefghi"))
    data = docx_bytes("<w:p><w:r><w:t>&i;</w:t></w:r></w:p>",
                      prolog=f"<!DOCTYPE w:document [{ents}]>")
    rejected(data, "unreadable_file")


def test_malformed_xml_rejected():
    data = zip_bytes({"word/document.xml": "<w:document>" + SECRET})
    rejected(data, "unreadable_file")


def test_not_a_docx():
    rejected(SECRET.encode() * 5, "unreadable_file")
    rejected(zip_bytes({"other.xml": SECRET}), "unreadable_file")


def test_zip_limits_apply_to_docx():
    rejected(zip_bytes({"word/document.xml": b"<a/>",
                        "word/media/bomb.bin": b"\0" * (3 * 1024 * 1024)}),
             "payload_too_large")
    rejected(zip_bytes({"word/document.xml": "<a/>", "../x.xml": SECRET}),
             "unreadable_file")
    rejected(set_encrypted_flag(docx_bytes(para(SECRET))), "unreadable_file")


def test_styles_part_is_parsed_safely_too():
    bad = STYLES.replace('<?xml version="1.0" encoding="UTF-8"?>',
                         '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY e '
                         '"x">]>')
    rejected(docx_bytes(para("Text."), styles=bad), "unreadable_file")


def test_missing_defusedxml_is_an_ingest_error_not_a_crash(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "defusedxml", None)
    monkeypatch.setitem(sys.modules, "defusedxml.ElementTree", None)
    rejected(docx_bytes(para(SECRET)), "unsupported_file")


# --- CLI -------------------------------------------------------------------------

def test_cli_checks_a_docx(tmp_path, capsys):
    path = tmp_path / "chapter.docx"
    path.write_bytes(docx_bytes(para("Results", style="berschrift1")
                                + para(AGENT)))
    assert cli.main(["check", str(path), "--no-metrics"]) == 1
    assert "G104" in capsys.readouterr().out


# --- P29 real-document bench: deeply nested input must be refused, not crash --

@pytest.mark.parametrize("depth", [400, 2000])
def test_deeply_nested_tables_are_refused_cleanly(depth):
    # 400 levels is small enough to pass the size guards and reach the
    # depth cap; 2000 is refused earlier by the zip-bomb ratio guard. Either
    # refusal is clean; a RecursionError (the bug) is not.
    inner = para("A cell.")
    for _ in range(depth):
        inner = f"<w:tbl><w:tr><w:tc>{inner}</w:tc></w:tr></w:tbl>"
    with pytest.raises(IngestError) as e:
        load_bytes(NAME, docx_bytes(inner))
    assert e.value.code == ("unreadable_file" if depth == 400
                            else "payload_too_large")


def test_deeply_nested_hyperlinks_are_refused_cleanly():
    inner = run("x")
    for _ in range(1500):
        inner = f"<w:hyperlink>{inner}</w:hyperlink>"
    rejected(docx_bytes(f"<w:p>{inner}</w:p>"), "unreadable_file")


def test_ordinary_nesting_still_reads():
    inner = para("A nested cell.")
    for _ in range(6):
        inner = f"<w:tbl><w:tr><w:tc>{inner}</w:tc></w:tr></w:tbl>"
    assert "A nested cell." in load(inner).original
