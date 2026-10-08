"""LT001 — optional grammar tier via LanguageTool (open source, explicitly
non-AI — honors the no-LLM decision).

Two ways to reach LanguageTool:

- **local** (default): `pip install language-tool-python` and Java 17+; the
  library downloads and runs LanguageTool on this machine (no text leaves it).
- **remote**: set `RESEARCHLY_LT_URL` (e.g. `http://localhost:8010`) and the
  tier talks to that LanguageTool server instead of spawning Java. This is
  how the hosted engine reaches its sidecar container (ARCHITECTURE.md
  ADR-03). health.py probes the server and says so when it is unreachable.

When unavailable, this rule abstains and health.py reports why.

We keep only genuine grammar findings (agreement, verb forms, articles,
word confusion) and drop LanguageTool's spelling (S001's job) and style
(our rules' job) categories, so the tiers never double-flag.
"""

from __future__ import annotations

import os
import threading
import time

from .document import Document
from .engine import Category, Suggestion, rule


def _apply_bundled_lt() -> bool:
    """Point language_tool_python at a bundled LanguageTool, if shipped.

    Standalone installers vendor LanguageTool-<version> inside the app so
    the 259 MB first-run download never happens. language_tool_python
    honours LTP_JAR_DIR_PATH; set it before the tool is constructed. An
    explicit user-set value is never overridden. Returns True when a
    bundled copy is in use.
    """
    if os.environ.get("LTP_JAR_DIR_PATH"):
        return True                       # user/build already chose one
    from .health import bundled_languagetool
    lt_dir = bundled_languagetool()
    if lt_dir is None:
        return False
    os.environ["LTP_JAR_DIR_PATH"] = str(lt_dir)
    return True

_LOCK = threading.Lock()
_TOOL = None
_FAILED = False
# Why the tier is down, for health.py to report. Before this, a missing
# package or JRE made LT001 silently inert forever and the writer had no
# way to tell grammar checking from a clean document.
_STATE = "unstarted"        # unstarted | ready | no_package | no_java | error
_DETAIL = ""
_LOCALE = None              # the locale the live tool was built for
_URL = None                 # the remote server the live tool talks to, if any
_FAILED_AT = 0.0            # monotonic time of the last failed start

# Remote LanguageTool (the hosted engine's sidecar). Unlike a missing JRE, an
# unreachable server is usually transient — the sidecar is still starting, or
# was restarted — so a failure is retried after this many seconds instead of
# being sticky for the life of the process.
REMOTE_ENV = "RESEARCHLY_LT_URL"
REMOTE_RETRY_S = 15.0
# Total time one grammar check may take against the remote server.
# language_tool_python's default is 300 s per try, which would hold a hosted
# request hostage to a hung sidecar. A 1M-character document (the contract's
# cap) took ~27 s of LanguageTool time on a 4-core dev machine; 120 s leaves
# room for a slower vCPU. After one failure the client is dropped and
# re-probed (3 s), so a dead sidecar costs one slow request, not every one.
REMOTE_TIMEOUT_S = 120
# check() goes through the client's _query_server, which tries twice on an
# I/O error, each try with the full per-try timeout. The S1 code review found
# the real worst case was therefore 2 x REMOTE_TIMEOUT_S under the engine
# lock, past Cloud Run's 300 s request limit on a large document. The budget
# above is split across the tries instead.
REMOTE_CLIENT_TRIES = 2


def remote_url():
    """The LanguageTool server to use instead of a local JVM, or None.

    Normalised once, here, so the health probe and the client agree on the
    address: a scheme is added when missing (`localhost:8010`), and the base
    keeps any path (`http://host/lt`). Both then append `/v2/...` to it.
    """
    url = (os.environ.get(REMOTE_ENV) or "").strip().rstrip("/")
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    return url

# 'misspelling' is included because LanguageTool files rule-based word
# confusions (a/an, their/there) under it — dictionary spelling is still
# excluded via the MORFOLOGIK/HUNSPELL prefixes (that's S001's job).
KEEP_ISSUE_TYPES = {"grammar", "duplication", "inconsistency",
                    "typographical", "misspelling"}
SKIP_RULE_PREFIXES = ("MORFOLOGIK", "HUNSPELL", "SPELLER")
# Typographical rules that misfire on scientific prose. Measured on two
# independent corpora the first time this tier actually ran:
#
#   UPPERCASE_SENTENCE_START  39.7% of LT001 flags on the accepted-thesis
#     corpus, 26.4% on AESW's editor-approved published prose — the single
#     noisiest rule in both. Scientific sentences legitimately open with a
#     symbol, a variable, a gene name or a unit ("$R_0$ exceeds one",
#     "log-normal priors were used"), and PDF extraction manufactures more
#     by splitting sentences mid-clause.
#   EN_UNPAIRED_QUOTES / EN_UNPAIRED_BRACKETS  fire on the asymmetric
#     bracketing of numeric citations and interval notation.
#   DASH_RULE / GERMAN_QUOTES  fire on en-dashed year ranges (2003—2012)
#     and on quotation marks in reference lists.
SKIP_TYPO_RULES = {
    "WHITESPACE_RULE", "COMMA_PARENTHESIS_WHITESPACE",
    "UPPERCASE_SENTENCE_START", "EN_UNPAIRED_QUOTES",
    "EN_UNPAIRED_BRACKETS", "DASH_RULE", "GERMAN_QUOTES",
}

# LanguageTool rules that misread scientific prose (P31, Q3). Counted on the
# accepted-thesis corpus (566 LT001 flags) and the owner's own methods
# report (11 LT001 flags, every one a misread); a rule is listed only when
# nearly all of its hits were wrong.
#   EN_COMPOUNDS_* / MAKER_COMPOUNDS  "policy makers", "sub-tropical",
#     "hyper-parameters", "well behaved", "Viet Nam" (the WHO spelling):
#     75 thesis hits + 4 in the report. Open, hyphenated and closed forms
#     are all in published use; the journal's house style decides.
#   NON_STANDARD_WORD  67/67 on maths or R code ("log=T", "Bc,t").
#   THE_SUPERLATIVE  37/39 on "least squares" or "nearest facility".
#   NUMBERS_IN_WORDS  identifiers ("x0itj", "P1th", gene and strain names).
#   POSSESSIVE_APOSTROPHE  noun adjuncts ("odds ratio", "cases isolation").
#   I_LOWERCASE / THE_PUNCT  an index or variable named i or a ("aged a,").
#   EN_SPECIFIC_CASE  "southern Europe", "southern hemisphere": style.
#   ADMIT_ENJOY_VB  reads a purpose infinitive as a complement ("were
#     considered to estimate" -> "considered estimating" changes the meaning).
SKIP_MISREAD_RULES = {
    "MAKER_COMPOUNDS", "NON_STANDARD_WORD", "THE_SUPERLATIVE",
    "NUMBERS_IN_WORDS", "POSSESSIVE_APOSTROPHE", "I_LOWERCASE", "THE_PUNCT",
    "EN_SPECIFIC_CASE", "ADMIT_ENJOY_VB",
}
# EN_DIACRITICS_REPLACE_*: "numeraire" -> "numéraire", "naive" -> "naïve".
# English accepts both spellings, so this is a preference (P33).
SKIP_MISREAD_PREFIXES = ("EN_COMPOUNDS_", "EN_DIACRITICS_REPLACE_")

# LanguageTool rules that duplicate one of Researchly's own rules on the same
# span. The S1 end-to-end run showed two cards for one "the the". Researchly's
# rule wins because it carries a named source and a bulk-safe fix.
#   ENGLISH_WORD_REPEAT_RULE  ->  W207 doubled-word
SKIP_COVERED_RULES = {"ENGLISH_WORD_REPEAT_RULE"}


def get_tool(locale: str = "en-US"):
    """Lazy local LanguageTool; returns None if unavailable.

    Records WHY it is unavailable in module state so health.py can tell the
    writer whether grammar checking is off because the package is missing,
    because there is no JRE, or because they turned it off.
    """
    global _TOOL, _FAILED, _STATE, _DETAIL, _LOCALE, _URL
    url = remote_url()
    if url is not None:
        return _get_remote_tool(locale, url)
    with _LOCK:
        if _TOOL is not None and _LOCALE == locale and _URL is None:
            return _TOOL
        if _FAILED and _URL is None:      # a remote failure says nothing
            return None                   # about the local JVM
        _URL = None
        try:
            import language_tool_python
        except Exception as e:
            _FAILED, _STATE = True, "no_package"
            _DETAIL = str(e)
            _TOOL = None
            return None
        # Standalone builds ship LanguageTool inside the app; point the
        # wrapper at it BEFORE construction so nothing downloads.
        _apply_bundled_lt()
        # language_tool_python finds the JVM with shutil.which("java"), so a
        # keg-only Homebrew JDK is invisible to it however correctly it was
        # installed. Put the real one on PATH first.
        from .health import ensure_java_on_path
        if not ensure_java_on_path():
            _FAILED, _STATE = True, "no_java"
            _DETAIL = "no working Java 17+ runtime found"
            _TOOL = None
            return None
        try:
            if _TOOL is not None:               # locale changed: rebuild
                try:
                    _TOOL.close()
                except Exception:
                    pass
                _TOOL = None
            _TOOL = language_tool_python.LanguageTool(locale)
            _LOCALE, _STATE, _DETAIL = locale, "ready", ""
            _FAILED, _URL = False, None
        except Exception as e:
            _FAILED = True
            _DETAIL = str(e)
            # A missing JRE is the common case and has a different remedy
            # from a failed download, so separate them. Note this must be a
            # real probe: macOS ships a `java` stub that exists on PATH but
            # runs nothing, which is how this tier stayed dead unnoticed.
            from .health import java_available
            _STATE = "error" if java_available() else "no_java"
            _TOOL = None
    return _TOOL


def _get_remote_tool(locale: str, url: str):
    """LanguageTool client for a server at `url` (no JVM in this process).

    The server is probed with a real check before the client is built
    (capability, not presence — health.probe_remote), because constructing
    the client would otherwise wait language_tool_python's 300 s timeout on
    a hung server.
    """
    global _TOOL, _FAILED, _STATE, _DETAIL, _LOCALE, _URL, _FAILED_AT
    with _LOCK:
        if _TOOL is not None and _LOCALE == locale and _URL == url:
            return _TOOL
        if _FAILED and _URL == url and \
                time.monotonic() - _FAILED_AT < REMOTE_RETRY_S:
            return None
        try:
            import language_tool_python
        except Exception as e:
            _FAILED, _STATE, _FAILED_AT = True, "no_package", time.monotonic()
            _DETAIL, _URL = str(e), url
            _TOOL = None
            return None
        from .health import probe_remote
        ok, why = probe_remote(url, use_cache=False)
        if not ok:
            _FAILED, _STATE, _FAILED_AT = True, "error", time.monotonic()
            _DETAIL, _URL = why, url
            _TOOL = None
            return None
        try:
            if _TOOL is not None:
                try:
                    _TOOL.close()
                except Exception:
                    pass
                _TOOL = None
            # The trailing slash keeps a path in the base: the client
            # urljoins "v2/" onto it, which would otherwise replace the last
            # path segment (http://host/lt -> http://host/v2/).
            tool = language_tool_python.LanguageTool(locale,
                                                     remote_server=url + "/")
            # Instance attribute shadows the class's 300 s default; per try.
            tool._TIMEOUT = REMOTE_TIMEOUT_S / REMOTE_CLIENT_TRIES
            _TOOL, _LOCALE, _URL = tool, locale, url
            _FAILED, _STATE, _DETAIL = False, "ready", ""
        except Exception as e:
            # Type name only: the client's error text can include the
            # server's response body, which is not ours to repeat.
            _FAILED, _STATE, _FAILED_AT = True, "error", time.monotonic()
            _DETAIL = f"LanguageTool server did not start a session " \
                      f"({type(e).__name__})"
            _URL, _TOOL = url, None
    return _TOOL


def _drop_remote_tool() -> None:
    """After a failed remote check: forget the client and back off.

    The next check re-probes (a few seconds at most) once REMOTE_RETRY_S has
    passed, instead of every request waiting out the full request timeout
    on a sidecar that has died.
    """
    global _TOOL, _FAILED, _FAILED_AT
    with _LOCK:
        _TOOL = None
        _FAILED, _FAILED_AT = True, time.monotonic()


def available(locale: str = "en-US") -> bool:
    return get_tool(locale) is not None


def state() -> tuple[str, str]:
    """(state, detail) without forcing a load. See _STATE for the values."""
    return _STATE, _DETAIL


def reset() -> None:
    """Allow a retry after a failure.

    `_FAILED` is deliberately sticky so a broken tier costs one attempt, not
    one per check. But a user who installs a JDK while the Word server is
    running would otherwise be told "grammar is off" until they restarted
    the process, with no hint that a restart was the answer.
    """
    global _TOOL, _FAILED, _STATE, _DETAIL, _LOCALE, _URL, _FAILED_AT
    with _LOCK:
        if _TOOL is not None:
            try:
                _TOOL.close()
            except Exception:
                pass
        _TOOL = None
        _FAILED = False
        _STATE, _DETAIL, _LOCALE = "unstarted", "", None
        _URL, _FAILED_AT = None, 0.0
    from .health import reset_java_cache
    reset_java_cache()


@rule("LT001", "grammar", Category.CORRECTION,
      "Grammar (agreement, verb forms, articles) via LanguageTool.",
      'The grammar layer, delegated to LanguageTool, a mature open-source '
      'rule engine that runs beside the engine. Only genuine grammar '
      "categories are used; spelling and style belong to Researchly's own "
      'rules, so nothing is flagged twice. If grammar checking is '
      'unavailable, the health notice says so.',
      plain=('A grammar check: things like a verb that does not match its '
             'subject, a missing article, or the wrong word form. It comes from '
             'LanguageTool, an open-source grammar checker that runs with '
             'Researchly and never sends your text anywhere else.'),
      source="LanguageTool",
      tier="grammar", fix_safety="review")
def lt001_grammar(doc, document: Document):
    cfg = getattr(document, "config", None)
    if cfg is not None and cfg.grammar_tier is False:   # explicitly off
        return
    locale = getattr(cfg, "locale", None) or "en-US"
    tool = get_tool(locale)
    if tool is None:
        return
    global _STATE, _DETAIL
    try:
        matches = tool.check(document.masked)
    except Exception as e:
        # Never str(e): a failed check's message can carry the server's
        # response body, which may echo the document. health.py shows this
        # detail on a status endpoint other people can read (hosted mode),
        # so it gets the exception type and nothing else.
        _STATE = "error"
        _DETAIL = f"LanguageTool check failed ({type(e).__name__})"
        if remote_url() is not None:
            _drop_remote_tool()
        return
    # A check that works is the ground truth: recover from an earlier
    # failure (a sidecar restart) instead of reporting "error" forever.
    _STATE, _DETAIL = "ready", ""
    for m in matches:
        # attribute names vary across language_tool_python versions
        issue = (getattr(m, "rule_issue_type", None)
                 or getattr(m, "ruleIssueType", "") or "").lower()
        rule_id = (getattr(m, "rule_id", None)
                   or getattr(m, "ruleId", "") or "")
        err_len = (getattr(m, "error_length", None)
                   or getattr(m, "errorLength", 0) or 0)
        if issue not in KEEP_ISSUE_TYPES:
            continue
        if (rule_id.startswith(SKIP_RULE_PREFIXES + SKIP_MISREAD_PREFIXES)
                or rule_id in SKIP_TYPO_RULES
                or rule_id in SKIP_MISREAD_RULES
                or rule_id in SKIP_COVERED_RULES):
            continue
        start = m.offset
        end = m.offset + err_len
        # masked regions are spaces; never flag inside them
        if not document.masked[start:end].strip():
            continue
        # ...nor across them: LanguageTool reads "An $\\exp(1)$ prior" as
        # "An prior" and "$a$, $b$," as two commas in a row.
        if document.touches_masked(start, end):
            continue
        repl = m.replacements[0] if m.replacements else None
        yield Suggestion(
            message=f"{m.message} [{rule_id}]",
            start=start, end=end,
            replacement=repl)
