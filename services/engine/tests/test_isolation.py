"""Hosted requests are multi-tenant: no file on the server may change them.

A planted ~/.researchly/config.toml, ~/.researchly/dictionary.txt and a
.researchly.toml in the working directory would — in the CLI — mute a rule,
show preferences and teach the spell-checker a word. The service must
ignore all three. A control asserts the plant is effective for the CLI path,
so the test cannot pass merely because the files were written wrongly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from researchly import config as config_mod
from researchly import spelling

from researchly_service import _core

from conftest import analyze, make_settings, rule_ids  # noqa: F401

MISSPELT = "transmisionn"          # S001 flags it unless a dictionary knows it
TEXT = (f"Discussion\n\nThe {MISSPELT} model was calibrated by the "
        "authors using weekly data. The effect was very large.\n")
PLANTED_TOML = f"""
[rules]
disable = ["G104", "S001"]
show_preferences = true

[dictionary]
words = ["{MISSPELT}"]
"""


@pytest.fixture
def planted_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    user_dir = home / ".researchly"
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text(PLANTED_TOML, encoding="utf-8")
    (user_dir / "dictionary.txt").write_text(MISSPELT + "\n",
                                            encoding="utf-8")
    cwd = tmp_path / "project"
    cwd.mkdir()
    (cwd / ".researchly.toml").write_text(PLANTED_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(cwd)
    # Point the core at the planted HOME exactly as it would compute it at
    # import time under that HOME — i.e. simulate isolation never happening.
    monkeypatch.setattr(config_mod, "USER_DIR", user_dir)
    monkeypatch.setattr(config_mod, "USER_CONFIG_FILE",
                        user_dir / "config.toml")
    monkeypatch.setattr(spelling, "USER_DICT_FILE", user_dir / "dictionary.txt")
    yield home
    _core.isolate()


def test_the_plant_is_effective_for_the_local_cli_path(planted_home):
    cfg = config_mod.load()
    assert {"G104", "S001"} <= cfg.disabled and cfg.show_preferences
    assert MISSPELT in spelling.user_dictionary()


def test_planted_user_and_project_config_have_no_effect(planted_home,
                                                        make_client,
                                                        monkeypatch):
    # Belt and braces: the service must never resolve config from files.
    def no_load(*a, **kw):
        raise AssertionError("the service called config.load()")
    monkeypatch.setattr(config_mod, "load", no_load)

    c = make_client()                     # lifespan runs _core.isolate()
    assert not Path(config_mod.USER_CONFIG_FILE).exists()
    assert not Path(spelling.USER_DICT_FILE).exists()

    r = analyze(c, TEXT)
    assert r.status_code == 200
    ids = rule_ids(r)
    assert "G104" in ids, "planted [rules] disable leaked into the service"
    assert "S001" in ids, "planted disable / dictionary leaked"
    assert any(s["text"] == MISSPELT for s in r.json()["suggestions"]
               if s["rule_id"] == "S001"), "planted dictionary leaked"
    body = r.json()
    assert not any(s["category"] == "preference" for s in body["suggestions"])
    assert body["hidden_preferences"] >= 1, \
        "planted show_preferences leaked"


def test_request_options_still_apply(planted_home, make_client):
    c = make_client()
    r = analyze(c, TEXT, disabled_rules=["G104"], show_preferences=True)
    ids = rule_ids(r)
    assert "G104" not in ids and "S001" in ids
    assert r.json()["hidden_preferences"] == 0


def test_options_do_not_leak_between_requests(client):
    muted = analyze(client, TEXT, disabled_rules=["G104"])
    assert "G104" not in rule_ids(muted)
    assert "G104" in rule_ids(analyze(client, TEXT))


def test_core_is_found_without_a_repo_layout(tmp_path):
    """The image has /app/researchly_service and no packages/ above it; the
    import helper must not assume the repo's depth (it once did:
    IndexError on Path.parents[3] at container start)."""
    import shutil
    import subprocess
    import sys

    app = tmp_path / "app"
    shutil.copytree(Path(_core.__file__).parent, app / "researchly_service")
    core_root = Path(__import__("researchly").__file__).parent.parent
    proc = subprocess.run(
        [sys.executable, "-c",
         "import researchly_service._core as c; print(c.repo_core_dir())"],
        cwd=app, capture_output=True, text=True,
        env={"PYTHONPATH": str(core_root), "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, proc.stderr[-500:]
    assert proc.stdout.strip() == "None"
