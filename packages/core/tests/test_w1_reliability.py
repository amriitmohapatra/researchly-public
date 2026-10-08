"""Regression tests for the W1 reliability defects.

Each test pins a specific way the tool could damage or misreport a
document. The JavaScript-side fixes (wrong-instance Apply, tracked-changes
restore, citation fields, auto-recheck) are covered here at the seam the
client depends on — the payload the server sends — plus static assertions
on taskpane.js for the parts that only exist in the browser.
"""

import re
import sys
from pathlib import Path

import pytest

from researchly import api
from researchly.document import Document
from researchly.transform import polish, _expletive_edits

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "word-addin"))
import server as addin_server  # noqa: E402

WEB = Path(__file__).resolve().parents[3] / "apps" / "word-addin" / "web"
TASKPANE_JS = (WEB / "taskpane.js").read_text(encoding="utf-8")

NLP = api.get_nlp()


# --- defect 4: Polish deleted masked markup ---------------------------------

@pytest.mark.parametrize("text,kind,must_keep", [
    ("There are $n$ parameters that vary across settings.", "markdown", "$n$"),
    ("There are [@smith2020] studies that report this.", "markdown",
     "[@smith2020]"),
    ("There are \\cite{jones} studies that report this.", "latex",
     "\\cite{jones}"),
    ("There are $\\beta_i$ terms that capture heterogeneity.", "markdown",
     "$\\beta_i$"),
])
def test_polish_never_eats_masked_markup(text, kind, must_keep):
    """G105 matched on the mask and spliced into the source.

    Masked regions are spaces, so `\\s+` in the expletive pattern swallowed
    one: "There are $n$ parameters that vary" came back as "Parameters
    vary". Polish promises equations and citations cannot be altered.
    """
    assert must_keep in polish(text, NLP, kind=kind).rewritten


def test_polish_still_rewrites_clean_expletives():
    """The fix must not silence the transform on ordinary prose."""
    out = polish("There are three factors that drive transmission.",
                 NLP, kind="plain").rewritten
    assert out == "Three factors drive transmission."


def test_polish_cascade_still_reaches_fixpoint():
    out = polish("It is important to note that there are three factors "
                 "that drive X.", NLP, kind="plain").rewritten
    assert out == "Three factors drive X."


def test_expletive_edits_skip_spans_covering_a_mask():
    doc = Document.from_text("There are $n$ items that matter.", "markdown")
    assert _expletive_edits(doc.masked, doc.original) == []
    clean = Document.from_text("There are two items that matter.", "markdown")
    assert len(_expletive_edits(clean.masked, clean.original)) == 1


# --- defect 2: Apply could rewrite the wrong copy ---------------------------

def _check(paragraphs):
    return addin_server.run_check({"paragraphs": paragraphs})


def test_locator_sends_the_full_span_not_a_prefix():
    """A 180-char truncated needle can match somewhere the span does not."""
    long_phrase = ("We utilize " + "an extremely elaborate and deliberately "
                   "verbose measurement apparatus " * 4 + "in order to test.")
    result = _check([{"text": long_phrase, "style": "Normal"}])
    for s in result["suggestions"]:
        assert s["snippet"] == s["expected"] or s["exact"] is False
        if s["exact"]:
            assert s["snippet"] == long_phrase[s["start_in_para"]:
                                               s["end_in_para"]]


def test_occurrence_index_is_counted_on_the_needle_actually_searched():
    """The count used to be taken on a truncated snippet while the client
    searched for something else, so the index could point at the wrong hit."""
    text = ("We utilize a model. Later we utilize a model again, and then "
            "we utilize a model once more.")
    result = _check([{"text": text, "style": "Normal"}])
    hits = [s for s in result["suggestions"] if s["rule_id"] == "W201"]
    assert len(hits) == 3
    for s in hits:
        prefix = text[:s["start_in_para"]]
        assert s["occurrence"] == prefix.count(s["snippet"])
        # and the index really does select this span, not another
        spans = [m.start() for m in re.finditer(re.escape(s["snippet"]), text)]
        assert spans[s["occurrence"]] == s["start_in_para"]


def test_payload_carries_what_the_client_needs_to_verify():
    result = _check([{"text": "We utilize a model.", "style": "Normal"}])
    s = result["suggestions"][0]
    for field in ("snippet", "expected", "exact", "occurrence", "para",
                  "start_in_para", "end_in_para"):
        assert field in s, f"client cannot verify without {field}"


def test_client_verifies_position_before_replacing():
    """findRange must confirm the document still holds the expected text."""
    assert "para.text.substring(s.start_in_para, s.end_in_para) === expected" \
        in TASKPANE_JS


def test_client_no_longer_clamps_the_occurrence_index():
    """Math.min(occurrence, len-1) silently retargeted the last match."""
    assert "Math.min(s.occurrence" not in TASKPANE_JS


def test_client_refuses_an_ambiguous_document_wide_match():
    """The fallback used to take items[0] unconditionally."""
    assert "bodyResults.items.length === 1" in TASKPANE_JS
    assert "return bodyResults.items[0];" not in TASKPANE_JS


# --- defect 3: tracked changes were never restored --------------------------

def test_client_captures_and_restores_change_tracking():
    assert "beginTracking" in TASKPANE_JS and "endTracking" in TASKPANE_JS
    assert 'ctx.document.load("changeTrackingMode")' in TASKPANE_JS
    assert "ctx.document.changeTrackingMode = prior;" in TASKPANE_JS
    # restore must be in a finally so a failed edit cannot leave it on
    assert TASKPANE_JS.count("await endTracking(ctx, prior);") >= 2


def test_no_stale_reference_to_the_old_tracking_helper():
    assert "maybeEnableTracking" not in TASKPANE_JS


# --- defect 8: citation fields destroyed by insertText ----------------------

def test_client_refuses_to_edit_across_a_word_field():
    assert "overlapsField" in TASKPANE_JS
    assert "range.fields" in TASKPANE_JS
    # both the per-suggestion apply and the polish insert must be guarded
    assert TASKPANE_JS.count("await overlapsField(ctx,") >= 2


# --- defect 7: auto-recheck fired every 4 seconds regardless of edits -------

def test_both_sides_of_the_change_comparison_are_normalized():
    """body.text uses \\r, the paragraph join used \\n, so they could never
    be equal and a full check ran every 4s whether or not anything changed."""
    assert "function normalizeBody" in TASKPANE_JS
    assert "return normalizeBody(body.text);" in TASKPANE_JS
    assert "state.lastText = normalizeBody(" in TASKPANE_JS


# --- defect 6: table cells were treated as prose ----------------------------

def test_table_paragraphs_are_recorded_and_excluded_from_metrics():
    prose = {"text": "We estimated the reproduction number from case data "
                     "using a renewal model fitted to daily incidence.",
             "style": "Normal"}
    cells = [{"text": t, "style": "Normal", "kind": "table"}
             for t in ("Parameter", "Value", "beta", "0.42", "gamma", "0.10")]
    doc = Document.from_word([prose] + cells)
    assert len(doc.table_spans) == 6
    assert doc.in_table(doc.para_offsets[1])
    assert not doc.in_table(doc.para_offsets[0])

    with_tables = api.analyze([prose] + cells, nlp=NLP)
    without = api.analyze([prose], nlp=NLP)
    assert (with_tables.metrics.mean_sentence_len
            == without.metrics.mean_sentence_len), \
        "table cells dragged the sentence-length read-out"


def test_a_table_cell_cannot_re_section_the_document():
    """A cell reading 'Methods' must not push the rest into §methods."""
    paragraphs = [
        {"text": "Discussion", "style": "Heading 1"},
        {"text": "Methods", "style": "Normal", "kind": "table"},
        {"text": "These findings prove that the intervention works.",
         "style": "Normal"},
    ]
    doc = Document.from_word(paragraphs)
    assert doc.section_at(doc.para_offsets[2]) == "discussion"


# --- defect 5: silent coverage gap ------------------------------------------

def test_check_reports_what_it_did_not_read():
    """Office JS body.paragraphs excludes footnotes, headers, text boxes.
    Not saying so reads as 'nothing to flag' rather than 'not looked at'."""
    result = _check([{"text": "We utilize a model.", "style": "Normal"}])
    cov = result["coverage"]
    assert cov["paragraphs"] == 1
    assert "footnotes" in cov["not_checked"]
    assert "headers and footers" in cov["not_checked"]


def test_client_renders_the_coverage_note_and_tier_status():
    assert "function coverageNote" in TASKPANE_JS
    assert "function renderTiers" in TASKPANE_JS
    assert "renderTiers(data.health);" in TASKPANE_JS


# --- grammar tier precision (measured once LT001 could actually run) --------

def test_noisy_typographical_rules_are_suppressed():
    """LT001 went live for the first time in P17 and immediately pushed the
    thesis-corpus noise floor 10.4 -> 16.4/1000w, past the project's own
    ~11 reject threshold.

    UPPERCASE_SENTENCE_START was the single noisiest rule on BOTH corpora
    (39.7% of LT001 flags on accepted theses, 26.4% on AESW's published
    prose): scientific sentences legitimately open with a symbol or a
    lowercase variable. Suppressing it and four sibling typographical rules
    cut LT001's thesis flags by 65% (1,713 -> 592) and the floor to
    12.5/1000w, for 0.4pp of recall.
    """
    from researchly import rules_grammar as rg
    assert "UPPERCASE_SENTENCE_START" in rg.SKIP_TYPO_RULES
    for rule_id in ("EN_UNPAIRED_QUOTES", "EN_UNPAIRED_BRACKETS",
                    "DASH_RULE", "GERMAN_QUOTES"):
        assert rule_id in rg.SKIP_TYPO_RULES, rule_id
    # the genuine grammar categories must survive the cull
    assert "SUBJECT_VERB_AGREEMENT" not in rg.SKIP_TYPO_RULES
    assert "EN_A_VS_AN" not in rg.SKIP_TYPO_RULES
    assert "grammar" in rg.KEEP_ISSUE_TYPES


@pytest.mark.skipif(not __import__("researchly.health", fromlist=["x"])
                    .java_available(),
                    reason="no Java 17+ — grammar tier cannot run")
def test_grammar_tier_catches_real_errors_but_not_symbol_openers():
    text = ("The results has been analysed. $x$ denotes the rate. "
            "A important finding are reported.")
    ids = {(s.rule_id, s.text) for s in
           api.analyze(text, kind="markdown", nlp=NLP).suggestions}
    lt = {t for rid, t in ids if rid == "LT001"}
    assert "has" in lt, "subject-verb agreement must still fire"
    assert "A" in lt, "a/an must still fire"
    assert "denotes" not in lt, "a symbol-opened sentence must not be flagged"


# --- lazy rule registration -------------------------------------------------

def test_ping_reports_a_populated_registry_from_a_cold_start():
    """Rules register on import, and check() imports them lazily. Anything
    reporting on the registry before a first check has to trigger that, or
    the taskpane status line reads "0 rules" on a perfectly healthy engine.

    Must run in a fresh interpreter: once the rule modules are imported,
    re-importing them is a no-op, so an in-process test cannot see the bug.
    """
    import subprocess
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from researchly.engine import REGISTRY;"
         "print('before', len(REGISTRY));"
         "from researchly import api;"
         "print('after', api.ensure_rules_loaded())" % str(root)],
        capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr
    before, after = out.stdout.split()[1], out.stdout.split()[3]
    assert int(before) == 0, "registry was already populated; test is void"
    assert int(after) >= 30, f"cold start reported only {after} rules"


def test_server_ping_does_not_report_zero_rules():
    handler_src = (Path(__file__).resolve().parents[3]
                   / "apps" / "word-addin" / "server.py").read_text()
    ping_block = handler_src.split('self.path == "/ping"')[1][:600]
    assert "api.ensure_rules_loaded()" in ping_block
    assert "len(REGISTRY)" not in ping_block
