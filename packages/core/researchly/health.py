"""Engine health: which checking tiers are actually running.

The defect this exists to kill: LT001 (grammar) was registered like any
other rule and called on every check, but if `language_tool_python` or Java
was missing it returned nothing, forever, without a word. A clean result and
a dead grammar engine looked identical. The same was true of a missing spaCy
model in a packaged app, and of a missing symspellpy.

`engine_status()` never raises and never blocks on a download. Surfaces call
it after loading and render one status line per tier; `probe=True` is the
"Test grammar engine" button, which is allowed to be slow.
"""

from __future__ import annotations

import glob
import importlib.util
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Config

SPACY_MODEL = "en_core_web_sm"

# Where this engine is running. Health details are promises to the writer
# ("nothing leaves this machine"), so they must be true for the deployment
# they are read in. The hosted engine sets RESEARCHLY_MODE=service; the CLI,
# LSP and desktop surfaces leave it unset and keep the local wording.
MODE_ENV = "RESEARCHLY_MODE"


def service_mode() -> bool:
    """Is this the hosted engine service (not a local surface)?"""
    return (os.environ.get(MODE_ENV) or "").strip().lower() == "service"


@dataclass
class TierStatus:
    tier: str          # parser | spelling | grammar | gec | files
    label: str         # human name for the UI
    ok: bool           # is this tier contributing suggestions right now?
    state: str         # ready | missing | disabled | error | unstarted
    detail: str = ""   # why, in one line
    remedy: str = ""   # what the user can do about it

    def to_dict(self) -> dict:
        return {"tier": self.tier, "label": self.label, "ok": self.ok,
                "state": self.state, "detail": self.detail,
                "remedy": self.remedy}


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


_JAVA_OK: Optional[bool] = None
_JAVA_PATH: Optional[str] = None

# Where a JDK actually lives when it is not on PATH. Homebrew's openjdk is
# keg-only: `brew install openjdk@17` succeeds, reports success, and links
# nothing — so `java` still resolves to Apple's stub and the grammar tier
# stays dead. Requiring a sudo symlink to fix that is a bad answer; find it.
_JDK_GLOBS = (
    "/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",
    "/opt/homebrew/opt/openjdk*",
    "/usr/local/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",
    "/usr/local/opt/openjdk*",
    "/Library/Java/JavaVirtualMachines/*/Contents/Home",
    str(Path.home() / ".sdkman/candidates/java/current"),
    "/usr/lib/jvm/*",                       # linux
    "C:/Program Files/Java/*",              # windows
    "C:/Program Files/Eclipse Adoptium/*",
    "C:/Program Files/Microsoft/jdk*",
    "C:/Program Files/Amazon Corretto/*",
    "C:/Program Files/Zulu/*",
)

MIN_JAVA = 17

# On Windows the executable is java.exe; building "bin/java" there makes
# every existence check fail and the search silently find nothing.
JAVA_EXE = "java.exe" if os.name == "nt" else "java"


# --- bundled runtime discovery (P20: standalone installers) ----------------
#
# The standalone builds ship every dependency INSIDE the artifact: a
# jlink-trimmed JRE at vendor/jre and a pre-downloaded LanguageTool at
# vendor/LanguageTool-<version>. Nothing downloads at first run and no
# system Java is required — but a machine WITHOUT the bundle behaves
# exactly as before (these helpers just return None).

VENDOR_ENV = "RESEARCHLY_VENDOR"      # explicit override; also used by tests


def vendor_dir() -> Optional[Path]:
    """The bundled-dependencies folder of a standalone build, if any.

    Checked in order: the RESEARCHLY_VENDOR env override; the py2app
    Resources directory (env RESOURCEPATH); PyInstaller's extraction dir
    (sys._MEIPASS, onefile) and the executable's folder (onedir, where
    modern PyInstaller puts support files under _internal/).
    """
    candidates: list[Path] = []
    env = os.environ.get(VENDOR_ENV)
    if env:
        candidates.append(Path(env))
    res = os.environ.get("RESOURCEPATH")               # py2app .app
    if res:
        candidates.append(Path(res) / "vendor")
    meipass = getattr(sys, "_MEIPASS", None)           # PyInstaller onefile
    if meipass:
        candidates.append(Path(meipass) / "vendor")
    if getattr(sys, "frozen", False):                  # PyInstaller onedir
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "vendor")
        candidates.append(exe_dir / "_internal" / "vendor")
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except Exception:
            continue
    return None


def bundled_java() -> Optional[str]:
    """Path to the bundle's own JRE executable, if this build ships one."""
    v = vendor_dir()
    if v is None:
        return None
    exe = v / "jre" / "bin" / JAVA_EXE
    try:
        return str(exe) if exe.exists() else None
    except Exception:
        return None


def bundled_languagetool() -> Optional[Path]:
    """The bundle's pre-downloaded LanguageTool-<version> folder, if any.

    Points language_tool_python straight at the shipped jar directory (via
    LTP_JAR_DIR_PATH, set in rules_grammar) so the 259 MB first-run
    download never happens on an installed standalone build.
    """
    v = vendor_dir()
    if v is None:
        return None
    try:
        for cand in sorted(v.glob("LanguageTool*"), reverse=True):
            if cand.is_dir():
                return cand
    except Exception:
        pass
    return None


def _runs(exe: str) -> Optional[int]:
    """Major version if this java executable actually runs, else None.

    Apple's /usr/bin/java stub exists and is executable but only prints
    "Unable to locate a Java Runtime" and exits non-zero. Presence is not
    availability — run it.
    """
    try:
        import subprocess
        proc = subprocess.run([exe, "-version"], capture_output=True,
                              timeout=20)
        if proc.returncode != 0:
            return None
        text = (proc.stderr or b"").decode(errors="replace") + \
               (proc.stdout or b"").decode(errors="replace")
        m = re.search(r'version "?(\d+)(?:\.(\d+))?', text)
        if not m:
            return None
        major = int(m.group(1))
        # 1.8.0_xxx style → the minor is the real major
        if major == 1 and m.group(2):
            major = int(m.group(2))
        return major
    except Exception:
        return None


def find_java() -> Optional[str]:
    """Path to a working java >= MIN_JAVA, searched beyond PATH. Cached."""
    global _JAVA_PATH, _JAVA_OK
    if _JAVA_OK is not None:
        return _JAVA_PATH

    candidates: list[str] = []
    # A standalone build's own JRE wins over everything: it is the one
    # runtime whose version and presence the build verified.
    shipped = bundled_java()
    if shipped:
        candidates.append(shipped)
    env_home = os.environ.get("JAVA_HOME")
    if env_home:
        candidates.append(str(Path(env_home) / "bin" / JAVA_EXE))
    on_path = shutil.which("java")
    if on_path:
        candidates.append(on_path)
    # macOS's own locator, which knows about /Library/Java installs
    try:
        import subprocess
        proc = subprocess.run(["/usr/libexec/java_home", "-v",
                               str(MIN_JAVA)], capture_output=True, timeout=15)
        if proc.returncode == 0:
            home = proc.stdout.decode(errors="replace").strip()
            if home:
                candidates.append(str(Path(home) / "bin" / JAVA_EXE))
    except Exception:
        pass
    for pattern in _JDK_GLOBS:
        for home in sorted(glob.glob(pattern), reverse=True):
            candidates.append(str(Path(home) / "bin" / JAVA_EXE))

    seen: set = set()
    fallback: Optional[str] = None
    for exe in candidates:
        if exe in seen or not Path(exe).exists():
            continue
        seen.add(exe)
        major = _runs(exe)
        if major is None:
            continue
        if major >= MIN_JAVA:
            _JAVA_PATH, _JAVA_OK = exe, True
            return exe
        fallback = fallback or exe        # runs, but too old — report it

    _JAVA_PATH, _JAVA_OK = fallback, False
    return None


def ensure_java_on_path() -> bool:
    """Make the discovered JDK visible to child processes.

    `language_tool_python` locates the JVM with `shutil.which("java")`, so a
    keg-only Homebrew JDK is invisible to it no matter that it is installed.
    Prepending the real bin directory to this process's PATH is enough, and
    is scoped to Researchly — nothing outside it is changed.
    """
    exe = find_java()
    if exe is None:
        return False
    bindir = str(Path(exe).parent)
    home = str(Path(exe).parent.parent)
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("JAVA_HOME", home)
    return True


def java_available() -> bool:
    """Is a usable Java >= MIN_JAVA reachable, on PATH or not?"""
    return find_java() is not None


def reset_java_cache() -> None:
    """Forget the probe result — after the user installs a JDK mid-session."""
    global _JAVA_OK, _JAVA_PATH
    _JAVA_OK = _JAVA_PATH = None


# --- remote LanguageTool (RESEARCHLY_LT_URL) ---------------------------------
#
# Capability, not presence: an open port proves nothing (the sidecar's JVM
# listens before LanguageTool has loaded its rules), so the probe runs a real
# check on a fixed synthetic sentence and requires a well-formed answer.

PROBE_TEXT = "This are a probe sentence."       # synthetic; never user text
PROBE_TIMEOUT_S = 3.0
PROBE_TTL_S = 10.0
_PROBE_CACHE: dict = {}      # url -> (monotonic time, ok, detail)


def probe_remote(url: str, timeout: float = PROBE_TIMEOUT_S,
                 use_cache: bool = True) -> tuple:
    """(ok, detail) for a LanguageTool server at `url`. Never raises.

    `detail` names the failure by exception type only — it is shown on a
    public status endpoint in hosted mode.
    """
    import time
    now = time.monotonic()
    if use_cache:
        hit = _PROBE_CACHE.get(url)
        if hit is not None and now - hit[0] < PROBE_TTL_S:
            return hit[1], hit[2]
    ok, detail = _probe_remote_uncached(url, timeout)
    _PROBE_CACHE[url] = (now, ok, detail)
    return ok, detail


def _probe_remote_uncached(url: str, timeout: float) -> tuple:
    import json
    import urllib.parse
    import urllib.request
    endpoint = url.rstrip("/") + "/v2/check"
    data = urllib.parse.urlencode(
        {"text": PROBE_TEXT, "language": "en-US"}).encode()
    try:
        req = urllib.request.Request(endpoint, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        if not isinstance(body, dict) or not isinstance(
                body.get("matches"), list):
            return False, "LanguageTool server answered, but not with " \
                          "a check result"
        return True, ""
    except Exception as e:
        return False, f"LanguageTool server is not responding " \
                      f"({type(e).__name__})"


def reset_probe_cache() -> None:
    _PROBE_CACHE.clear()


def _remote_grammar_status(cfg: Optional[Config], url: str,
                           probe: bool) -> TierStatus:
    """Grammar tier status when LanguageTool is a server, not a local JVM."""
    from . import rules_grammar

    hosted = service_mode()
    ready_detail = (
        "LanguageTool sidecar beside the engine, same region (text is "
        "checked in memory, never stored)" if hosted else
        f"LanguageTool server at {url} (text is sent to that server)")
    if hosted:
        remedy = ("the LanguageTool sidecar is down or still starting; "
                  "check its container logs (RESEARCHLY_LT_URL)")
    else:
        remedy = (f"start the server at {url} (e.g. docker run -p 8010:8010 "
                  f"erikvl87/languagetool) or unset {rules_grammar.REMOTE_ENV} "
                  f"to use a local LanguageTool")

    if not _installed("language_tool_python"):
        return TierStatus(
            "grammar", "Grammar", False, "missing",
            "language-tool-python is not installed",
            "pip install language-tool-python")

    state, detail = rules_grammar.state()
    if not probe:
        # If a check has already run, module state is the ground truth.
        if state == "ready":
            return TierStatus("grammar", "Grammar", True, "ready",
                              ready_detail)
        if state == "error":
            return TierStatus("grammar", "Grammar", False, "error",
                              detail or "LanguageTool server failed", remedy)
    # `probe` means "ask the server rather than trust module state", not
    # "bypass the cache": /v1/health is public and polled, and an uncached
    # probe cost the sidecar a real check per hit. PROBE_TTL_S bounds how
    # stale the answer can be.
    ok, why = probe_remote(url)
    if ok:
        return TierStatus("grammar", "Grammar", True, "ready", ready_detail)
    return TierStatus("grammar", "Grammar", False, "error", why, remedy)


def _parser_status(nlp=None) -> TierStatus:
    if nlp is not None:
        return TierStatus("parser", "Sentence parser", True, "ready",
                          f"{SPACY_MODEL} loaded")
    if not _installed("spacy"):
        return TierStatus(
            "parser", "Sentence parser", False, "missing",
            "spaCy is not installed",
            "pip install spacy")
    if not _installed(SPACY_MODEL):
        return TierStatus(
            "parser", "Sentence parser", False, "missing",
            f"the {SPACY_MODEL} model is not installed",
            f"python -m spacy download {SPACY_MODEL}")
    return TierStatus("parser", "Sentence parser", True, "unstarted",
                      "installed, not yet loaded")


def _spelling_status() -> TierStatus:
    if not _installed("symspellpy"):
        return TierStatus(
            "spelling", "Spelling", False, "missing",
            "symspellpy is not installed",
            "pip install symspellpy")
    # The hosted service has no personal dictionary until accounts land
    # (S2), so it must not claim one.
    detail = ("SymSpell + scientific lexicon" if service_mode() else
              "SymSpell + scientific lexicon + your dictionary")
    return TierStatus("spelling", "Spelling", True, "ready", detail)


def _grammar_status(cfg: Optional[Config], probe: bool) -> TierStatus:
    from . import rules_grammar

    if cfg is not None and cfg.grammar_tier is False:
        return TierStatus(
            "grammar", "Grammar", False, "disabled",
            "turned off in settings",
            "re-enable the grammar tier in settings")

    url = rules_grammar.remote_url()
    if url is not None:
        return _remote_grammar_status(cfg, url, probe)

    hosted = service_mode()
    ready_detail = (
        "LanguageTool inside the engine container (text is checked in "
        "memory, never stored)" if hosted else
        "local LanguageTool (nothing leaves this machine)")
    no_java_remedy = (
        "point RESEARCHLY_LT_URL at the LanguageTool sidecar (the engine "
        "image ships no Java)" if hosted else
        "brew install openjdk@17   (no symlink needed — it is found "
        "even when keg-only)")

    state, detail = rules_grammar.state()

    # If a check has already run, module state is the ground truth.
    if state == "ready":
        return TierStatus("grammar", "Grammar", True, "ready", ready_detail)
    if state == "no_package":
        return TierStatus(
            "grammar", "Grammar", False, "missing",
            "language-tool-python is not installed",
            "pip install language-tool-python")
    if state == "no_java":
        return TierStatus(
            "grammar", "Grammar", False, "missing",
            "no working Java 17+ runtime found (PATH, JAVA_HOME, Homebrew "
            "and /Library/Java were all searched)",
            no_java_remedy)
    if state == "error":
        return TierStatus(
            "grammar", "Grammar", False, "error",
            detail or "LanguageTool failed to start",
            "see OPTIONAL-grammar-tier.md")

    # state == "unstarted": nothing has forced a load yet.
    if not _installed("language_tool_python"):
        return TierStatus(
            "grammar", "Grammar", False, "missing",
            "language-tool-python is not installed",
            "pip install language-tool-python")
    if not java_available():
        return TierStatus(
            "grammar", "Grammar", False, "missing",
            "no working Java 17+ runtime found (PATH, JAVA_HOME, Homebrew "
            "and /Library/Java were all searched)",
            no_java_remedy)
    if probe:
        locale = getattr(cfg, "locale", None) or "en-US"
        ok = rules_grammar.available(locale)
        return _grammar_status(cfg, probe=False) if not ok else TierStatus(
            "grammar", "Grammar", True, "ready", ready_detail)
    return TierStatus(
        "grammar", "Grammar", True, "unstarted",
        "installed; starts on the first check "
        "(first run downloads LanguageTool, ~200 MB)")


def _gec_status(cfg: Optional[Config]) -> TierStatus:
    """Local non-generative edit tagger — scaffold present, model absent.

    Unlike the deterministic tiers, this one is OPT-IN: `gec = true` in
    `[tiers]` is required even when a backend is live, because a learned
    layer earns trust by being asked for (gec.py has the full contract).
    """
    from . import gec

    if cfg is not None and cfg.gec_tier is False:
        return TierStatus("gec", "Learned corrections", False, "disabled",
                          "turned off in settings",
                          "re-enable in settings")
    if not gec.available():
        return TierStatus(
            "gec", "Learned corrections", False, "missing",
            "no local model in this build (the tier abstains entirely)", "")
    if cfg is None or cfg.gec_tier is not True:
        return TierStatus(
            "gec", "Learned corrections", False, "disabled",
            "a local model is present but the tier is opt-in",
            "set  [tiers] gec = true  in settings to enable it")
    where = ("runs inside the engine; text is never stored"
             if service_mode() else "nothing leaves this machine")
    return TierStatus(
        "gec", "Learned corrections", True, "ready",
        f"local edit tagger ({gec.get_backend().version}) — {where}")


def _files_status() -> Optional[TierStatus]:
    """The file readers (researchly.ingest). Reported only when degraded:
    every surface reads LaTeX, but most never read a file, so a "ready"
    line would be noise in Word's status bar. Degraded is news everywhere:
    without pylatexenc LaTeX falls back to the regex masker, and without
    defusedxml .docx cannot be read at all."""
    missing = [m for m in ("pylatexenc", "defusedxml") if not _installed(m)]
    if not missing:
        return None
    effects = []
    if "pylatexenc" in missing:
        effects.append("LaTeX markup is masked by a simpler fallback")
    if "defusedxml" in missing:
        effects.append(".docx files cannot be read")
    return TierStatus("files", "File reading", False, "missing",
                      f"{' and '.join(missing)} not installed: "
                      f"{'; '.join(effects)}",
                      "pip install " + " ".join(missing))


def engine_status(cfg: Optional[Config] = None, nlp=None,
                  probe: bool = False) -> list[TierStatus]:
    """Status of every checking tier. Never raises; never downloads unless
    `probe` is set."""
    out = []
    for fn in (lambda: _parser_status(nlp),
               _spelling_status,
               lambda: _grammar_status(cfg, probe),
               lambda: _gec_status(cfg),
               _files_status):
        try:
            status = fn()
        except Exception as e:                       # health must never fail
            status = TierStatus("unknown", "Unknown", False, "error",
                                f"{type(e).__name__}: {e}")
        if status is not None:
            out.append(status)
    return out


def summary_line(statuses: list[TierStatus]) -> str:
    """One line for a status bar: 'Spelling · Grammar off (needs Java 17+)'."""
    ready = [s.label for s in statuses if s.ok and s.state in ("ready",
                                                              "unstarted")]
    # A tier with no remedy isn't installable by the user (the GEC tier in a
    # build that ships without it) — reporting it as "off" is noise, not news.
    down = [f"{s.label} off ({s.detail})" for s in statuses
            if not s.ok and (s.remedy or s.state in ("disabled", "error"))]
    parts = []
    if ready:
        parts.append(" · ".join(ready))
    parts.extend(down)
    return " · ".join(parts) if parts else "no tiers available"
