"""Tests for api.analyze — the single entry point all surfaces call."""

import pytest

from researchly import api
from researchly import config as config_mod
from researchly.config import Config
from researchly.document import Document
from researchly.engine import Category

NLP = api.get_nlp()

SAMPLE = ("We utilize a model in order to predict teh outcome. "
          "This proves that stratification matters.")


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Never read or write the user's real ~/.researchly during tests."""
    user_dir = tmp_path / "userhome" / ".researchly"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(config_mod, "USER_DIR", user_dir)
    monkeypatch.setattr(config_mod, "USER_CONFIG_FILE",
                        user_dir / "config.toml")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return user_dir, project


def test_analyze_returns_a_complete_payload(isolated):
    a = api.analyze(SAMPLE, nlp=NLP)
    assert a.suggestions
    assert a.counts
    assert a.metrics is not None
    assert a.health
    assert a.document is not None
    d = a.to_dict()
    assert set(d) == {"suggestions", "counts", "hidden_preferences",
                      "hidden_by_mode", "profile", "review", "narrative",
                      "checklist", "suggested_checklist",
                      "metrics", "sections_detected", "health", "config"}


def test_hidden_preferences_counted_without_a_second_run(isolated):
    """The count used to cost a whole extra pipeline pass."""
    a = api.analyze(SAMPLE, nlp=NLP)
    assert a.config.show_preferences is False
    assert all(s.category is not Category.PREFERENCE for s in a.suggestions)
    shown = api.analyze(SAMPLE, nlp=NLP, show_preferences=True)
    assert shown.hidden_preferences == 0
    # what was hidden before is present now
    assert len(shown.suggestions) == len(a.suggestions) + a.hidden_preferences


def test_suggestions_arrive_render_ready(isolated):
    """Surfaces must not have to reach back into REGISTRY."""
    for s in api.analyze(SAMPLE, nlp=NLP).suggestions:
        assert s.why and s.tier and s.fix_safety


def test_config_reaches_the_rules(isolated):
    """`disabled` from a project file must apply on every surface path."""
    _, project = isolated
    (project / ".researchly.toml").write_text('[rules]\ndisable = ["W201"]\n')
    ids = {s.rule_id for s in api.analyze(SAMPLE, nlp=NLP,
                                          near=project / "x.md").suggestions}
    assert "W201" not in ids
    assert "W202" in ids            # neighbouring rule still fires


def test_toml_dictionary_words_are_honoured(isolated):
    """spelling.py documented [dictionary] words since v0.5 and nothing ever
    populated it, so the setting silently did nothing."""
    _, project = isolated
    text = "The zzyzxine parameter was estimated."
    near = project / "x.md"
    assert "S001" in {s.rule_id for s in
                      api.analyze(text, nlp=NLP, near=near).suggestions}
    (project / ".researchly.toml").write_text(
        '[dictionary]\nwords = ["zzyzxine"]\n')
    assert "S001" not in {s.rule_id for s in
                          api.analyze(text, nlp=NLP, near=near).suggestions}


def test_overrides_beat_config_files(isolated):
    _, project = isolated
    (project / ".researchly.toml").write_text('[rules]\ndisable = ["W201"]\n')
    a = api.analyze(SAMPLE, nlp=NLP, near=project / "x.md",
                    disabled={"W202"})
    ids = {s.rule_id for s in a.suggestions}
    assert "W202" not in ids
    assert "W201" in ids


def test_accepts_text_paragraphs_and_paths(isolated, tmp_path):
    _, project = isolated
    from_text = api.analyze(SAMPLE, nlp=NLP)
    paragraphs = [{"text": "Methods", "style": "Heading 1"},
                  {"text": SAMPLE, "style": "Normal"}]
    from_word = api.analyze(paragraphs, nlp=NLP)
    path = project / "sample.md"
    path.write_text(SAMPLE)
    from_path = api.analyze(path, nlp=NLP)

    assert from_text.suggestions and from_word.suggestions
    assert from_path.suggestions
    assert "methods" in from_word.sections_detected


def test_word_paragraph_offsets_survive(isolated):
    """Suggestion offsets must still map back into the source paragraph."""
    paragraphs = [{"text": "Intro", "style": "Heading 1"},
                  {"text": SAMPLE, "style": "Normal"}]
    a = api.analyze(paragraphs, nlp=NLP)
    s = next(x for x in a.suggestions if x.rule_id == "W201")
    para, start_in = a.document.locate(s.start)
    assert paragraphs[para]["text"][start_in:start_in + len(s.text)] == s.text


def test_health_reports_the_grammar_tier(isolated):
    a = api.analyze(SAMPLE, nlp=NLP)
    grammar = next(t for t in a.health if t.tier == "grammar")
    assert a.grammar_ok == grammar.ok
    if not grammar.ok:
        assert grammar.detail          # never fail without saying why


def test_grammar_tier_can_be_switched_off(isolated):
    a = api.analyze(SAMPLE, nlp=NLP, cfg=Config(grammar_tier=False))
    grammar = next(t for t in a.health if t.tier == "grammar")
    assert grammar.state == "disabled"
    assert "LT001" not in {s.rule_id for s in a.suggestions}


def test_metrics_can_be_skipped(isolated):
    assert api.analyze(SAMPLE, nlp=NLP, with_metrics=False).metrics is None


def test_shared_nlp_has_the_raised_length_cap():
    """The CLI was the only surface that did not raise this, so it alone
    crashed instead of degrading on a long thesis."""
    assert api.get_nlp().max_length == api.MAX_LENGTH
    assert api.get_nlp() is api.get_nlp()


def test_one_parse_per_analyze(isolated, monkeypatch):
    """Guard the whole point of this module against regression."""
    calls = []
    real = NLP.__call__

    class Counting:
        max_length = api.MAX_LENGTH

        def __call__(self, text):
            calls.append(len(text))
            return real(text)

    api.analyze(SAMPLE, nlp=Counting())
    assert len(calls) == 1, f"expected 1 spaCy parse, got {len(calls)}"
