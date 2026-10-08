"""Tests for the Word add-in path: from_word documents + server /check."""

import sys
from pathlib import Path

import spacy

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "word-addin"))

from researchly.document import Document
from researchly.engine import check
import server as addin_server

NLP = spacy.load("en_core_web_sm")

PARAS = [
    {"text": "Methods", "style": "Heading1"},
    {"text": "Samples were incubated at 37 degrees before analysis.",
     "style": "Normal"},
    {"text": "Results", "style": "Heading 1"},
    {"text": "The pattern was first described by Anderson and May. "
             "We performed an estimation of the transmission rate.",
     "style": "Normal"},
]


def test_from_word_styles_define_sections():
    doc = Document.from_word(PARAS)
    assert [h.section for h in doc.headings] == ["methods", "results"]
    # heading text is masked
    assert "Methods" not in doc.masked and "Results" not in doc.masked
    # offsets: paragraph 3 starts after paragraphs 0-2 plus separators
    assert doc.para_offsets[1] == len("Methods") + 2
    assert doc.section_at(doc.para_offsets[1]) == "methods"
    assert doc.section_at(doc.para_offsets[3]) == "results"


def test_from_word_section_aware_rules():
    doc = Document.from_word(PARAS)
    found = [s.rule_id for s in check(doc, NLP, show_preferences=True)]
    assert "G104" in found      # agent-ful passive in Results fires
    assert "G102" in found      # buried action fires
    # the agentless passive in Methods stays quiet
    g104 = [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == "G104"]
    assert all(s.section == "results" for s in g104)


def test_locate_maps_back_to_paragraph():
    doc = Document.from_word(PARAS)
    hits = [s for s in check(doc, NLP, show_preferences=True)
            if s.rule_id == "G102"]
    assert hits
    para, start_in = doc.locate(hits[0].start)
    assert para == 3
    para_text = PARAS[3]["text"]
    end_in = hits[0].end - doc.para_offsets[para]
    assert para_text[start_in:end_in] == "performed an estimation of"


def test_unstyled_typed_heading_still_detected():
    paras = [
        {"text": "Discussion", "style": "Normal"},   # typed, not styled
        {"text": "This proves that stratification matters.",
         "style": "Normal"},
    ]
    doc = Document.from_word(paras)
    found = [s.rule_id for s in check(doc, NLP, show_preferences=True)]
    assert "C302" in found       # overclaim fires because section=discussion


def test_server_run_check_payload():
    result = addin_server.run_check({
        "paragraphs": PARAS,
        "disabled": [],
        "show_preferences": False,
    })
    assert result["sections_detected"] == ["methods", "results"]
    g102 = [s for s in result["suggestions"] if s["rule_id"] == "G102"]
    assert g102
    s = g102[0]
    assert s["para"] == 3
    assert s["snippet"] == "performed an estimation of"
    assert s["occurrence"] == 0
    assert "why" in s and len(s["why"]) > 40
    assert "metrics" in result and result["metrics"]["sentences"] >= 2


def test_server_respects_disabled_and_occurrence():
    paras = [{"text": "We utilize diaries and we utilize surveys.",
              "style": "Normal"}]
    r1 = addin_server.run_check({"paragraphs": paras})
    w201 = [s for s in r1["suggestions"] if s["rule_id"] == "W201"]
    assert len(w201) == 2
    assert w201[0]["occurrence"] == 0 and w201[1]["occurrence"] == 1
    r2 = addin_server.run_check({"paragraphs": paras, "disabled": ["W201"]})
    assert not [s for s in r2["suggestions"] if s["rule_id"] == "W201"]


# --- W2 (sprint items 1-2, 2026-08-14): shared config + review endpoint ----

def test_taskpane_never_persists_mutes_in_localstorage():
    """The W2 parity guarantee, pinned at the source level: the taskpane
    may only *delete* the legacy localStorage key (migration), never write
    it. A new localStorage settings store is exactly the regression the
    shared config layer exists to prevent."""
    js = (Path(__file__).resolve().parents[3] / "apps" / "word-addin" / "web"
          / "taskpane.js").read_text(encoding="utf-8")
    assert "localStorage.setItem" not in js
    assert "/config" in js                       # mutes go to the server
    assert "migrateLocalStorageMutes" in js      # legacy mutes migrate


def test_taskpane_has_the_five_tabs():
    html = (Path(__file__).resolve().parents[3] / "apps" / "word-addin" / "web"
            / "taskpane.html").read_text(encoding="utf-8")
    for tab in ("check", "review", "polish", "settings", "health"):
        assert f'data-tab="{tab}"' in html, f"missing tab {tab}"


def test_review_report_from_word_paragraphs():
    """/review's core: build_review accepts the from_word Document so
    style-based headings survive into the reviewer's brief."""
    from researchly import review as review_mod
    from researchly import api
    paras = [
        {"text": "Discussion", "style": "Heading1"},
        {"text": "We argue that spatial heterogeneity drives outbreak "
                 "size. Control must change now.", "style": "Normal"},
    ]
    doc = api.build_document(paras)
    r = review_mod.build_review(doc, NLP)
    assert "argument" in r
    codes = {link["code"] for link in r["argument"]["missing_links"]}
    assert "claim_without_warrant" in codes
    report = review_mod.render_review(r)
    assert "REVIEWER'S BRIEF" in report


def test_polish_reads_muted_rules_from_shared_config(tmp_path, monkeypatch):
    """The taskpane stopped sending `disabled`; the server must fall back
    to the shared config, so a muted rule stays out of Polish too."""
    from researchly import config as config_mod
    user_dir = tmp_path / ".researchly"
    user_dir.mkdir()
    monkeypatch.setattr(config_mod, "USER_DIR", user_dir)
    monkeypatch.setattr(config_mod, "USER_CONFIG_FILE",
                        user_dir / "config.toml")
    monkeypatch.chdir(tmp_path)

    from researchly import transform
    text = "We utilize a model in order to predict the outcome."

    r1 = transform.polish(text, NLP, disabled=config_mod.load().disabled)
    assert any(e["rule_id"] == "W201" for e in r1.to_dict()["edits"])

    config_mod.mute_rule("W201")
    r2 = transform.polish(text, NLP, disabled=config_mod.load().disabled)
    assert not any(e["rule_id"] == "W201" for e in r2.to_dict()["edits"])
