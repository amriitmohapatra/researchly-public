"""Tests for the shared surface layer: layered config and engine health.

These cover the defect class that motivated W0/W1: settings that reached
only some surfaces, and tiers that failed silently.
"""

import pytest

from researchly import config as config_mod
from researchly import health as health_mod


# --- config: layering -------------------------------------------------------

@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point user config at a temp dir; never touch the real ~/.researchly."""
    user_dir = tmp_path / "userhome" / ".researchly"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(config_mod, "USER_DIR", user_dir)
    monkeypatch.setattr(config_mod, "USER_CONFIG_FILE", user_dir / "config.toml")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return user_dir, project


def test_defaults_when_nothing_configured(isolated):
    cfg = config_mod.load()
    assert cfg.disabled == set()
    assert cfg.show_preferences is False
    assert cfg.locale == "en-US"
    assert cfg.document_type == "auto"
    assert cfg.grammar_tier is None          # "use if available", not "off"


def test_legacy_project_toml_still_read(isolated):
    """The historical [rules] shape must keep working."""
    _, project = isolated
    (project / ".researchly.toml").write_text(
        '[rules]\ndisable = ["W203", "G106"]\nshow_preferences = true\n')
    cfg = config_mod.load(project / "chapter.md")
    assert cfg.disabled == {"W203", "G106"}
    assert cfg.show_preferences is True


def test_project_layers_over_user(isolated):
    user_dir, project = isolated
    (user_dir / "config.toml").write_text(
        '[rules]\ndisable = ["W201"]\n[document]\nlocale = "en-GB"\n')
    (project / ".researchly.toml").write_text('[rules]\ndisable = ["G106"]\n')
    cfg = config_mod.load(project / "x.md")
    # disables accumulate across layers; locale survives from the user layer
    assert cfg.disabled == {"W201", "G106"}
    assert cfg.locale == "en-GB"


def test_project_can_reenable_a_user_muted_rule(isolated):
    user_dir, project = isolated
    (user_dir / "config.toml").write_text('[rules]\ndisable = ["W201"]\n')
    (project / ".researchly.toml").write_text('[rules]\nenable = ["W201"]\n')
    assert config_mod.load(project / "x.md").disabled == set()


def test_overrides_beat_files(isolated):
    _, project = isolated
    (project / ".researchly.toml").write_text('[rules]\ndisable = ["W201"]\n')
    cfg = config_mod.load(project / "x.md", show_preferences=True,
                          disabled={"C303"})
    assert cfg.show_preferences is True
    assert cfg.disabled == {"C303"}
    # None overrides are ignored, not applied
    assert config_mod.load(project / "x.md",
                           show_preferences=None).show_preferences is False


def test_invalid_enum_values_are_ignored(isolated):
    _, project = isolated
    (project / ".researchly.toml").write_text(
        '[document]\ntype = "haiku"\nlocale = "kl-KL"\n')
    cfg = config_mod.load(project / "x.md")
    assert cfg.document_type == "auto"
    assert cfg.locale == "en-US"


def test_corrupt_toml_does_not_raise(isolated, capsys):
    _, project = isolated
    (project / ".researchly.toml").write_text('[rules\ndisable = broken')
    cfg = config_mod.load(project / "x.md")
    assert cfg.disabled == set()


def test_roundtrip_dumps_and_reload(isolated):
    _, project = isolated
    cfg = config_mod.Config(
        disabled={"G106", "W203"}, show_preferences=True, locale="en-GB",
        document_type="thesis-chapter", aggressiveness="light",
        grammar_tier=False, dictionary=["seroprevalence"])
    assert config_mod.save_user(cfg)
    back = config_mod.load()
    assert back.disabled == {"G106", "W203"}
    assert back.show_preferences is True
    assert back.locale == "en-GB"
    assert back.document_type == "thesis-chapter"
    assert back.aggressiveness == "light"
    assert back.grammar_tier is False
    assert "seroprevalence" in back.dictionary


def test_mute_persists_to_user_config_not_project(isolated):
    """A rule muted from any surface must follow the writer everywhere.

    This is the W0 parity guarantee: before it, a Word mute lived in browser
    localStorage and no other surface could see it.
    """
    user_dir, project = isolated
    assert config_mod.mute_rule("C303")
    assert (user_dir / "config.toml").exists()
    assert not (project / ".researchly.toml").exists()
    assert "C303" in config_mod.load().disabled
    assert config_mod.unmute_rule("C303")
    assert "C303" not in config_mod.load().disabled


# --- health -----------------------------------------------------------------

def test_engine_status_reports_every_tier():
    statuses = health_mod.engine_status(config_mod.Config())
    tiers = {s.tier for s in statuses}
    assert {"parser", "spelling", "grammar", "gec"} <= tiers
    for s in statuses:
        assert s.state in ("ready", "missing", "disabled", "error",
                           "unstarted")
        if not s.ok and s.state == "missing":
            assert s.detail, f"{s.tier} is down without saying why"


def test_file_readers_reported_only_when_missing(monkeypatch):
    """A missing pylatexenc silently degrades LaTeX masking on every
    surface; it must show up with a remedy. Installed, it adds no line."""
    statuses = health_mod.engine_status(config_mod.Config())
    assert "files" not in {s.tier for s in statuses}
    real = health_mod._installed
    monkeypatch.setattr(health_mod, "_installed",
                        lambda m: m != "pylatexenc" and real(m))
    files = [s for s in health_mod.engine_status(config_mod.Config())
             if s.tier == "files"]
    assert len(files) == 1 and not files[0].ok
    assert files[0].remedy == "pip install pylatexenc"
    assert "File reading off" in health_mod.summary_line(files)


def test_grammar_tier_reports_disabled_distinctly():
    """'You turned it off' must not look like 'it is broken'."""
    cfg = config_mod.Config(grammar_tier=False)
    grammar = next(s for s in health_mod.engine_status(cfg)
                   if s.tier == "grammar")
    assert grammar.ok is False
    assert grammar.state == "disabled"


@pytest.fixture(autouse=True)
def _clear_java_cache():
    health_mod.reset_java_cache()
    yield
    health_mod.reset_java_cache()


def _fake_java(monkeypatch, *, version_by_exe, existing):
    """Pretend a specific set of java binaries exist and report versions."""
    import subprocess

    monkeypatch.setattr(health_mod.shutil, "which",
                        lambda _: "/usr/bin/java" if "/usr/bin/java"
                        in existing else None)
    monkeypatch.setattr(health_mod, "_JDK_GLOBS", ())
    monkeypatch.setattr(health_mod.Path, "exists",
                        lambda self: str(self) in existing)

    class Result:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out, b""

    def run(cmd, *a, **k):
        exe = cmd[0]
        if exe == "/usr/libexec/java_home":
            return Result(1, b"")
        v = version_by_exe.get(exe)
        if v is None:
            return Result(1, b"Unable to locate a Java Runtime")
        return Result(0, f'openjdk version "{v}" 2026-01-01'.encode())

    monkeypatch.setattr(subprocess, "run", run)


def test_java_detection_rejects_apples_stub(monkeypatch):
    """macOS ships a /usr/bin/java stub that exists but runs nothing.

    which() finding it is exactly why the grammar tier looked installed on
    this machine while never once running. Presence is not availability.
    """
    monkeypatch.delenv("JAVA_HOME", raising=False)
    _fake_java(monkeypatch, version_by_exe={},
               existing={"/usr/bin/java"})
    assert health_mod.java_available() is False


def test_java_detection_accepts_a_real_jre(monkeypatch):
    monkeypatch.delenv("JAVA_HOME", raising=False)
    _fake_java(monkeypatch, version_by_exe={"/usr/bin/java": "17.0.20"},
               existing={"/usr/bin/java"})
    assert health_mod.java_available() is True


def test_java_too_old_is_not_accepted(monkeypatch):
    """LanguageTool needs 17+; an ancient JRE must not be reported ready."""
    monkeypatch.delenv("JAVA_HOME", raising=False)
    _fake_java(monkeypatch, version_by_exe={"/usr/bin/java": "1.8.0_411"},
               existing={"/usr/bin/java"})
    assert health_mod.java_available() is False


def test_keg_only_homebrew_jdk_is_found_off_path(monkeypatch):
    """THE bug this fixes: `brew install openjdk@17` succeeds, links nothing,
    and `java` still resolves to Apple's stub — so the grammar tier stayed
    dead on a machine that had a perfectly good JDK installed."""
    monkeypatch.delenv("JAVA_HOME", raising=False)
    brew = ("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
            "/bin/java")
    import subprocess

    monkeypatch.setattr(health_mod.shutil, "which", lambda _: "/usr/bin/java")
    monkeypatch.setattr(
        health_mod, "_JDK_GLOBS",
        ("/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",))
    monkeypatch.setattr(
        health_mod.glob, "glob",
        lambda p: ["/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk"
                   "/Contents/Home"])
    monkeypatch.setattr(health_mod.Path, "exists",
                        lambda self: str(self) in {"/usr/bin/java", brew})

    class Result:
        def __init__(self, rc, out):
            self.returncode, self.stderr, self.stdout = rc, out, b""

    def run(cmd, *a, **k):
        if cmd[0] == brew:
            return Result(0, b'openjdk version "17.0.20" 2026-07-21')
        return Result(1, b"Unable to locate a Java Runtime")

    monkeypatch.setattr(subprocess, "run", run)
    assert health_mod.find_java() == brew
    assert health_mod.java_available() is True


def test_ensure_java_on_path_exports_it_for_child_processes(monkeypatch):
    """language_tool_python locates the JVM with which("java"), so the
    discovered JDK has to reach the environment, not just our own check."""
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(health_mod, "_JAVA_OK", True)
    monkeypatch.setattr(health_mod, "_JAVA_PATH", "/opt/jdk/bin/java")
    assert health_mod.ensure_java_on_path() is True
    import os
    assert "/opt/jdk/bin" in os.environ["PATH"].split(os.pathsep)
    assert os.environ["JAVA_HOME"] == "/opt/jdk"


def test_grammar_tier_can_retry_after_a_jdk_appears():
    """_FAILED is sticky by design, but installing Java mid-session must not
    require restarting the Word server to be noticed."""
    from researchly import rules_grammar
    rules_grammar._FAILED = True
    rules_grammar._STATE = "no_java"
    rules_grammar.reset()
    assert rules_grammar.state()[0] == "unstarted"
    assert rules_grammar._FAILED is False


def test_health_never_raises(monkeypatch):
    """A broken probe must degrade to a status line, not kill the check."""
    def boom(*a, **k):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(health_mod, "_spelling_status", boom)
    statuses = health_mod.engine_status(config_mod.Config())
    assert any(s.state == "error" for s in statuses)


def test_summary_line_hides_tiers_with_no_remedy():
    """A tier absent by design is not something to nag the writer about."""
    statuses = [
        health_mod.TierStatus("spelling", "Spelling", True, "ready"),
        health_mod.TierStatus("gec", "Learned corrections", False, "missing",
                              "not installed in this build", ""),
    ]
    line = health_mod.summary_line(statuses)
    assert "Spelling" in line
    assert "Learned corrections" not in line


def test_candidate_paths_use_the_platform_executable_name(monkeypatch):
    """On Windows the binary is java.exe. Building "bin/java" there makes
    every existence check fail, so the search finds nothing and reports the
    tier missing on a machine with a perfectly good JDK.

    Patching health.JAVA_EXE rather than os.name: swapping os.name makes
    pathlib hand back WindowsPath objects it cannot instantiate here.
    """
    import subprocess

    monkeypatch.setenv("JAVA_HOME", "/opt/jdk17")
    monkeypatch.setattr(health_mod, "JAVA_EXE", "java.exe")
    monkeypatch.setattr(health_mod, "_JDK_GLOBS", ())
    monkeypatch.setattr(health_mod.shutil, "which", lambda _: None)

    tried = []

    monkeypatch.setattr(health_mod.Path, "exists",
                        lambda self: (tried.append(str(self)), False)[1])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))

    health_mod.find_java()
    assert any(t.endswith("java.exe") for t in tried), tried
    assert not any(t.endswith("bin/java") for t in tried), tried


def test_java_exe_matches_this_platform():
    import os as _os
    expected = "java.exe" if _os.name == "nt" else "java"
    assert health_mod.JAVA_EXE == expected


def test_windows_jdk_locations_are_searched():
    """A normal Windows JDK install must be found without configuration."""
    globs = " ".join(health_mod._JDK_GLOBS)
    for vendor in ("Program Files/Java", "Eclipse Adoptium", "Corretto"):
        assert vendor in globs, f"{vendor} not searched"


def test_jdk_found_with_a_finder_launch_environment(monkeypatch):
    """A .app launched from Finder gets launchd's minimal environment — no
    shell rc, no Homebrew on PATH, no JAVA_HOME. Relying on PATH would mean
    the packaged app had no grammar tier even though the terminal did.

    find_java() searches the filesystem for exactly this reason; this pins
    that it does not quietly regress into a PATH lookup.
    """
    import sys as _sys
    if _sys.platform != "darwin":
        pytest.skip("the Apple java-stub scenario only exists on macOS — "
                    "on Linux /usr/bin/java is a real JDK, so refusing it "
                    "would fail a healthy machine")
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    health_mod.reset_java_cache()

    found = health_mod.find_java()
    if found is None:
        pytest.skip("no JDK installed on this machine")
    assert "/usr/bin/java" != found, "resolved to Apple's stub"
    assert health_mod.ensure_java_on_path() is True
    import shutil
    assert shutil.which("java") == found
