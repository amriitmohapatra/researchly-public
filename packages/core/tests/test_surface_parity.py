"""Cross-surface parity: one engine, one settings store, one answer.

The W0 guarantee. Before it, each surface built its own pipeline and read its
own settings: `.researchly.toml` reached only the CLI and LSP, Word kept
muted rules in browser localStorage, the macOS app kept two toggles in its
own JSON file, and Windows had no settings at all. A rule muted in one place
stayed noisy everywhere else.
"""

import sys
from pathlib import Path

import pytest

from researchly import api
from researchly import config as config_mod

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "word-addin"))
import server as addin_server  # noqa: E402

NLP = api.get_nlp()

TEXT = ("We utilize a model in order to predict the outcome. "
        "This proves that stratification matters.")
PARAGRAPHS = [{"text": TEXT, "style": "Normal"}]


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    user_dir = tmp_path / "userhome" / ".researchly"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(config_mod, "USER_DIR", user_dir)
    monkeypatch.setattr(config_mod, "USER_CONFIG_FILE",
                        user_dir / "config.toml")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def _cli_rule_ids(path):
    """What `researchly check` would report."""
    from researchly import cli
    cfg = config_mod.load(path)
    return {s.rule_id for s in api.analyze(path, nlp=NLP, cfg=cfg).suggestions}


def _word_rule_ids():
    """What the Word taskpane would render."""
    return {s["rule_id"] for s in
            addin_server.run_check({"paragraphs": PARAGRAPHS})["suggestions"]}


def _desktop_rule_ids():
    """What the macOS/Windows panel would render — both call api.analyze
    with the config loaded from disk, exactly as here."""
    cfg = config_mod.load()
    return {s.rule_id for s in
            api.analyze(TEXT, kind="plain", nlp=NLP, cfg=cfg).suggestions}


def test_all_surfaces_agree_before_muting(isolated):
    path = isolated / "chapter.md"
    path.write_text(TEXT)
    assert _cli_rule_ids(path) == _word_rule_ids() == _desktop_rule_ids()
    assert "W201" in _word_rule_ids()


def test_a_mute_from_any_surface_reaches_all_of_them(isolated):
    """THE parity test. Mute once; every surface must go quiet."""
    path = isolated / "chapter.md"
    path.write_text(TEXT)
    assert "W201" in _cli_rule_ids(path)

    # the Word taskpane's mute button, via its /config endpoint
    assert config_mod.mute_rule("W201")

    assert "W201" not in _cli_rule_ids(path)
    assert "W201" not in _word_rule_ids()
    assert "W201" not in _desktop_rule_ids()
    # and the neighbouring rule is untouched
    assert "W202" in _word_rule_ids()


def test_unmuting_restores_every_surface(isolated):
    path = isolated / "chapter.md"
    path.write_text(TEXT)
    config_mod.mute_rule("W201")
    config_mod.unmute_rule("W201")
    assert "W201" in _cli_rule_ids(path)
    assert "W201" in _word_rule_ids()
    assert "W201" in _desktop_rule_ids()


def test_project_config_reaches_word_and_desktop(isolated):
    """.researchly.toml used to be invisible to everything but CLI and LSP."""
    project = isolated
    (project / ".researchly.toml").write_text('[rules]\ndisable = ["W202"]\n')
    assert "W202" not in _word_rule_ids()
    assert "W202" not in _desktop_rule_ids()


def test_dictionary_is_shared_across_surfaces(isolated, monkeypatch, tmp_path):
    """The one setting that always propagated — keep it that way."""
    from researchly import spelling
    dict_file = tmp_path / "dictionary.txt"
    monkeypatch.setattr(spelling, "USER_DICT_FILE", dict_file)
    spelling.user_dictionary.cache_clear() if hasattr(
        spelling.user_dictionary, "cache_clear") else None

    text = "The zzyzxine parameter was estimated."
    paragraphs = [{"text": text, "style": "Normal"}]
    before = {s["rule_id"] for s in
              addin_server.run_check({"paragraphs": paragraphs})["suggestions"]}
    assert "S001" in before

    assert spelling.add_to_user_dictionary("zzyzxine")
    after = {s["rule_id"] for s in
             addin_server.run_check({"paragraphs": paragraphs})["suggestions"]}
    assert "S001" not in after
    assert "S001" not in {s.rule_id for s in
                          api.analyze(text, nlp=NLP).suggestions}


def test_word_payload_carries_health_and_config(isolated):
    """The taskpane must be able to show which tiers are running."""
    result = addin_server.run_check({"paragraphs": PARAGRAPHS})
    assert "health" in result and result["health"]
    assert "config" in result
    assert {t["tier"] for t in result["health"]} >= {"parser", "spelling",
                                                     "grammar", "gec"}


def test_word_suggestions_still_carry_their_locators(isolated):
    """Rewiring onto api.analyze must not break Word's write-back path."""
    for s in addin_server.run_check(
            {"paragraphs": PARAGRAPHS})["suggestions"]:
        assert "para" in s and "snippet" in s and "occurrence" in s
        assert s["why"], f"{s['rule_id']} lost its explanation"
