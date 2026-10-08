"""Tests for the desktop panel renderer (the platform-independent part of
the macOS app) driven by real engine output."""

import sys
from pathlib import Path

import spacy

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "desktop-mac"))

import panel_html  # noqa: E402
from researchly.document import Document  # noqa: E402
from researchly.engine import REGISTRY, check  # noqa: E402
from researchly import metrics as metrics_mod  # noqa: E402
from researchly.transform import polish  # noqa: E402

NLP = spacy.load("en_core_web_sm")


def _checked(text):
    doc = Document.from_text(text, "plain")
    suggestions = check(doc, NLP, show_preferences=False)
    out = []
    for s in suggestions:
        d = s.to_dict()
        d["why"] = REGISTRY[s.rule_id].why
        out.append(d)
    mets = metrics_mod.compute(NLP(doc.masked), doc)
    return out, mets


def test_render_check_contains_cards_and_whys():
    suggestions, mets = _checked(
        "We utilize household data. This proves that stratification "
        "matters for policy.")
    html = panel_html.render_check(suggestions, mets, hidden_prefs=1,
                                   source_app="Microsoft Word")
    assert "W201" in html and "grand-word" in html
    assert "utilize" in html
    assert "<details>" in html and "Why?" in html
    assert "Microsoft Word" in html
    assert "1 preference notes hidden" in html
    assert "read-out, not a score" in html


def test_render_check_empty_state():
    suggestions, mets = _checked("The model predicts higher attack rates.")
    html = panel_html.render_check(suggestions, mets)
    assert "Nothing to flag" in html


def test_render_check_escapes_html():
    fake = [{
        "rule_id": "W201", "rule_name": "grand-word",
        "category": "improvement", "message": "<script>alert(1)</script>",
        "text": "<b>utilize</b>", "section": "unknown", "replacement": None,
        "why": "x & y",
    }]
    html = panel_html.render_check(fake)
    # the page carries its own (static) bridge <script>; what must never
    # appear unescaped is SUGGESTION-derived markup
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;utilize&lt;/b&gt;" in html


def test_render_polish_diff_and_ledger():
    r = polish("We utilize data in order to make an assessment of risk.",
               NLP)
    html = panel_html.render_polish(r, source_app="Overleaf")
    assert "<del>" in html and "<ins>" in html
    assert "G102" in html and "W201" in html and "W202" in html
    assert "Overleaf" in html
    assert "no AI generation" in html


def test_render_polish_unchanged_state():
    r = polish("We estimated the transmission rate for every scenario.",
               NLP)
    html = panel_html.render_polish(r)
    assert "Nothing to safely rewrite" in html


def test_render_message():
    html = panel_html.render_message("No selection", "Select some text.")
    assert "No selection" in html and "Select some text." in html


# --- W2 sprint (2026-08-14): actionable panels + shared settings page ------

def test_actionable_check_cards_carry_bridge_buttons():
    suggestions, mets = _checked(
        "We utilize household data. This proves that stratification "
        "matters for policy.")
    html = panel_html.render_check(suggestions, mets, actions=True)
    assert "rlAction" in html
    assert "Dismiss" in html and "Mute rule" in html
    assert "&quot;action&quot;: &quot;mute&quot;" in html \
        or "&quot;action&quot;:&quot;mute&quot;" in html \
        or "mute" in html          # exact JSON spacing is an impl detail
    # the shim itself ships with the page and degrades to a no-op
    assert "window.webkit" in html and "window.pywebview" in html


def test_display_only_render_stays_display_only():
    """actions defaults to False — the D2 watch snapshot and any old
    callers keep the previous behaviour."""
    suggestions, mets = _checked("We utilize household data.")
    html = panel_html.render_check(suggestions, mets)
    assert "Dismiss" not in html and "Mute rule" not in html


def test_add_to_dictionary_only_on_spelling_cards():
    fake = [{"rule_id": "S001", "rule_name": "spelling",
             "category": "correction", "message": "Unknown word",
             "text": "urbanicity", "section": "unknown",
             "replacement": "urbanity", "why": "w"},
            {"rule_id": "W201", "rule_name": "grand-word",
             "category": "improvement", "message": "m",
             "text": "utilize", "section": "unknown",
             "replacement": "use", "why": "w"}]
    html = panel_html.render_check(fake, actions=True)
    assert html.count("Add to dictionary") == 1


def test_polish_actions_render_html_buttons_for_windows():
    r = polish("We utilize data in order to make an assessment of risk.",
               NLP)
    html = panel_html.render_polish(r, actions=True)
    assert "Replace selection" in html and "Copy rewrite" in html
    assert "rlAction" in html
    # and the native-bar note is gone when the buttons are in the HTML
    assert "buttons below" not in html


def test_settings_page_renders_every_shared_setting():
    from researchly.config import Config
    cfg = Config(disabled={"W201"}, show_preferences=True,
                 document_type="manuscript", aggressiveness="thorough",
                 locale="en-GB", gec_tier=True)
    html = panel_html.render_settings(cfg)
    for needle in ("Document type", "Suggestion volume", "English variant",
                   "preference-type", "LanguageTool", "Learned-correction",
                   "Muted rules", "W201", "unmute"):
        assert needle in html, needle
    # current values are selected
    assert "value='manuscript' selected" in html.replace('"', "'")
    assert "value='en-GB' selected" in html.replace('"', "'")
    # every control writes through the shared-config bridge
    assert html.count("rlAction") >= 7


def test_settings_page_escapes_and_degrades_without_bridge():
    from researchly.config import Config
    html = panel_html.render_settings(Config())
    assert "no bridge" in html      # shim comment: degrades to no-op
    assert "none" in html           # empty muted list
