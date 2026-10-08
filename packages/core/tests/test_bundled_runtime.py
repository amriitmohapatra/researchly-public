"""P20 standalone installers: bundled JRE + LanguageTool discovery.

The standalone builds vendor every dependency inside the artifact
(vendor/jre, vendor/LanguageTool-<v>). These tests pin the discovery
logic with a fake vendor tree — no Java, no LanguageTool, no network.
"""

import os
import stat
import sys

import pytest

from researchly import health as health_mod
from researchly import rules_grammar


@pytest.fixture(autouse=True)
def clean_java_cache(monkeypatch):
    monkeypatch.delenv(health_mod.VENDOR_ENV, raising=False)
    monkeypatch.delenv("LTP_JAR_DIR_PATH", raising=False)
    health_mod.reset_java_cache()
    yield
    health_mod.reset_java_cache()


def _fake_vendor(tmp_path, java_version="21.0.1", with_lt=True):
    vendor = tmp_path / "vendor"
    bindir = vendor / "jre" / "bin"
    bindir.mkdir(parents=True)
    java = bindir / health_mod.JAVA_EXE
    java.write_text(
        "#!/bin/sh\n"
        f"echo 'openjdk version \"{java_version}\" 2026-01-01' >&2\n"
        "exit 0\n")
    java.chmod(java.stat().st_mode | stat.S_IEXEC)
    if with_lt:
        lt = vendor / "LanguageTool-6.8"
        lt.mkdir()
        (lt / "languagetool-server.jar").write_bytes(b"jar")
    return vendor


needs_sh = pytest.mark.skipif(sys.platform.startswith("win"),
                              reason="fake java is a shell script")


def test_no_vendor_means_no_bundle_and_no_behaviour_change():
    assert health_mod.vendor_dir() is None
    assert health_mod.bundled_java() is None
    assert health_mod.bundled_languagetool() is None


def test_vendor_env_override_is_discovered(tmp_path, monkeypatch):
    vendor = _fake_vendor(tmp_path)
    monkeypatch.setenv(health_mod.VENDOR_ENV, str(vendor))
    assert health_mod.vendor_dir() == vendor
    assert health_mod.bundled_java() == str(
        vendor / "jre" / "bin" / health_mod.JAVA_EXE)
    assert health_mod.bundled_languagetool() == vendor / "LanguageTool-6.8"


def test_py2app_resources_dir_is_discovered(tmp_path, monkeypatch):
    """A Finder-launched .app exposes RESOURCEPATH; vendor lives under it."""
    vendor = _fake_vendor(tmp_path)
    monkeypatch.setenv("RESOURCEPATH", str(tmp_path))
    assert health_mod.vendor_dir() == vendor


@needs_sh
def test_bundled_jre_outranks_every_system_java(tmp_path, monkeypatch):
    """find_java() must pick the shipped JRE first — it is the one runtime
    the build verified — even on a machine with a working system Java."""
    vendor = _fake_vendor(tmp_path)
    monkeypatch.setenv(health_mod.VENDOR_ENV, str(vendor))
    health_mod.reset_java_cache()
    assert health_mod.find_java() == str(
        vendor / "jre" / "bin" / health_mod.JAVA_EXE)


@needs_sh
def test_too_old_bundled_jre_is_not_used(tmp_path, monkeypatch):
    """A broken bundle (Java < 17) must fall through to the system search
    rather than silently killing the grammar tier."""
    vendor = _fake_vendor(tmp_path, java_version="1.8.0_392")
    monkeypatch.setenv(health_mod.VENDOR_ENV, str(vendor))
    health_mod.reset_java_cache()
    found = health_mod.find_java()
    assert found != str(vendor / "jre" / "bin" / health_mod.JAVA_EXE)


def test_bundled_languagetool_sets_the_wrapper_env(tmp_path, monkeypatch):
    vendor = _fake_vendor(tmp_path)
    monkeypatch.setenv(health_mod.VENDOR_ENV, str(vendor))
    assert rules_grammar._apply_bundled_lt() is True
    assert os.environ["LTP_JAR_DIR_PATH"] == str(
        vendor / "LanguageTool-6.8")


def test_user_set_ltp_path_is_never_overridden(tmp_path, monkeypatch):
    vendor = _fake_vendor(tmp_path)
    monkeypatch.setenv(health_mod.VENDOR_ENV, str(vendor))
    monkeypatch.setenv("LTP_JAR_DIR_PATH", "/somewhere/else")
    assert rules_grammar._apply_bundled_lt() is True
    assert os.environ["LTP_JAR_DIR_PATH"] == "/somewhere/else"


def test_no_bundle_leaves_the_env_alone(monkeypatch):
    assert rules_grammar._apply_bundled_lt() is False
    assert "LTP_JAR_DIR_PATH" not in os.environ
