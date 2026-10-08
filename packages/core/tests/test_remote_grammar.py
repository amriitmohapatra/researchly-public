"""Remote LanguageTool (RESEARCHLY_LT_URL) and hosted-mode health wording.

The hosted engine reaches LanguageTool as a sidecar server instead of a local
JVM (ARCHITECTURE.md ADR-03). These tests pin:

- the tier uses the server when the env var is set, and never starts Java;
- health PROBES the server (a real check, not an open port) and reports a
  reason and a remedy when it is unreachable — never a silent tier;
- a failed check never copies the server's error text (which can echo the
  document) into the health detail;
- an unreachable sidecar is retried after a back-off, not dead forever;
- health wording is truthful for the deployment: the desktop/CLI keep
  "nothing leaves this machine", the hosted service never claims it.

A fake LanguageTool server (stdlib http.server) makes the happy and failure
paths testable offline. Set RESEARCHLY_TEST_LT_URL to also run against a
real server (e.g. `docker run -p 8010:8010 erikvl87/languagetool`).
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer

import pytest

from researchly import health, rules_grammar
from researchly.config import Config

CANARY = "CANARY-LT-5e1d"
UNREACHABLE = "http://127.0.0.1:9"        # discard port: connection refused


# --- fixtures ---------------------------------------------------------------

_GLOBALS = ("_TOOL", "_FAILED", "_STATE", "_DETAIL", "_LOCALE", "_URL",
            "_FAILED_AT")


@pytest.fixture(autouse=True)
def _isolated_grammar_state(monkeypatch):
    """Save and restore rules_grammar's module state WITHOUT closing a local
    LanguageTool another test file started (restarting the JVM is slow)."""
    saved = {k: getattr(rules_grammar, k) for k in _GLOBALS}
    for k, v in (("_TOOL", None), ("_FAILED", False), ("_STATE", "unstarted"),
                 ("_DETAIL", ""), ("_LOCALE", None), ("_URL", None),
                 ("_FAILED_AT", 0.0)):
        setattr(rules_grammar, k, v)
    health.reset_probe_cache()
    monkeypatch.delenv(rules_grammar.REMOTE_ENV, raising=False)
    monkeypatch.delenv(health.MODE_ENV, raising=False)
    yield
    for k, v in saved.items():
        setattr(rules_grammar, k, v)
    health.reset_probe_cache()


class _FakeLT(BaseHTTPRequestHandler):
    """Just enough of LanguageTool's v2 HTTP API."""
    mode = "ok"                 # ok | broken_check | garbage | hang
    checks = 0
    probes = 0
    prefix = ""                 # serve under a path, e.g. "/lt"
    hang_s = 0.0

    def log_message(self, *a):  # keep test output quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith(type(self).prefix + "/v2/languages"):
            self._send(200, json.dumps([
                {"name": "English (US)", "code": "en", "longCode": "en-US"},
                {"name": "English (GB)", "code": "en", "longCode": "en-GB"}]))
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(
            self.rfile.read(n).decode())
        text = (form.get("text") or [""])[0]
        if not self.path.startswith(type(self).prefix + "/v2/check"):
            return self._send(404, "{}")
        if type(self).mode == "garbage":
            return self._send(200, "<html>not languagetool</html>",
                              "text/html")
        is_probe = text == health.PROBE_TEXT
        if type(self).mode == "hang" and not is_probe:
            import time
            time.sleep(type(self).hang_s)
            return self._send(200, json.dumps({"matches": []}))
        if is_probe:
            type(self).probes += 1
        else:
            type(self).checks += 1
        if type(self).mode == "broken_check" and not is_probe:
            # A server error that echoes the submitted text back — the worst
            # case for anything that copies str(exception) somewhere public.
            return self._send(500, f"Internal error while checking: {text}",
                              "text/plain")
        matches = []
        i = text.find("are")
        if i >= 0:
            matches.append({
                "message": "Possible agreement error.",
                "shortMessage": "", "offset": i, "length": 3,
                "replacements": [{"value": "is"}],
                "context": {"text": text, "offset": i, "length": 3},
                "sentence": text, "type": {"typeName": "Other"},
                "rule": {"id": "THIS_NNS_VB", "description": "agreement",
                         "issueType": "grammar",
                         "category": {"id": "GRAMMAR", "name": "Grammar"}},
                "ignoreForIncompleteSentence": False,
                "contextForSureMatch": 0,
            })
        self._send(200, json.dumps({"matches": matches}))


@pytest.fixture
def fake_lt(monkeypatch):
    _FakeLT.mode, _FakeLT.checks, _FakeLT.probes = "ok", 0, 0
    _FakeLT.prefix, _FakeLT.hang_s = "", 0.0
    server = HTTPServer(("127.0.0.1", 0), _FakeLT)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, url)
    yield url
    server.shutdown()
    server.server_close()


def _grammar(statuses):
    return next(s for s in statuses if s.tier == "grammar")


def _no_java(monkeypatch):
    """Make any attempt to start a local JVM fail the test."""
    def boom():
        raise AssertionError("remote mode must not look for or start Java")
    monkeypatch.setattr(health, "ensure_java_on_path", boom)


# --- remote: happy path -----------------------------------------------------

def test_remote_url_is_read_from_env(monkeypatch):
    assert rules_grammar.remote_url() is None
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, "  http://lt:8010/  ")
    assert rules_grammar.remote_url() == "http://lt:8010"


def test_remote_server_is_used_and_java_is_never_started(fake_lt,
                                                          monkeypatch):
    _no_java(monkeypatch)
    tool = rules_grammar.get_tool("en-US")
    assert tool is not None
    assert rules_grammar.state() == ("ready", "")
    assert tool._url.startswith(fake_lt)
    # per-try timeout x the client's tries == the total budget
    assert tool._TIMEOUT * rules_grammar.REMOTE_CLIENT_TRIES == rules_grammar.REMOTE_TIMEOUT_S


def test_remote_lt001_fires_through_the_engine(fake_lt, monkeypatch):
    _no_java(monkeypatch)
    from researchly.api import analyze
    a = analyze("These results are robust.", cfg=Config())
    lt = [s for s in a.suggestions if s.rule_id == "LT001"]
    assert lt and lt[0].text == "are" and lt[0].tier == "grammar"
    assert _grammar(a.health).ok


def test_health_probes_remote_with_a_real_check(fake_lt):
    st = _grammar(health.engine_status(Config(), probe=True))
    assert st.ok and st.state == "ready"
    assert fake_lt in st.detail                 # desktop: says where text goes
    assert "nothing leaves this machine" not in st.detail


def test_repeated_health_checks_reuse_the_cached_probe(fake_lt):
    """/v1/health is public and polled; each call must not cost the sidecar
    a fresh check. The security review (S1) found probe=True bypassed the
    TTL cache, so every health hit made a new 3-second-timeout request."""
    for _ in range(5):
        st = _grammar(health.engine_status(Config(), probe=True))
        assert st.ok
    assert _FakeLT.probes == 1
    health.reset_probe_cache()                   # TTL over -> probed again
    _grammar(health.engine_status(Config(), probe=True))
    assert _FakeLT.probes == 2


def test_probe_rejects_a_server_that_is_not_languagetool(fake_lt):
    _FakeLT.mode = "garbage"
    ok, detail = health.probe_remote(fake_lt, use_cache=False)
    assert not ok and detail


# --- remote: failure paths --------------------------------------------------

def test_unreachable_server_is_reported_with_reason_and_remedy(monkeypatch):
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, UNREACHABLE)
    _no_java(monkeypatch)
    assert rules_grammar.get_tool("en-US") is None
    assert rules_grammar.state()[0] == "error"
    for probe in (False, True):
        st = _grammar(health.engine_status(Config(), probe=probe))
        assert not st.ok and st.state == "error"
        assert "not responding" in st.detail
        assert st.remedy and "RESEARCHLY_LT_URL" in st.remedy
        assert "nothing leaves this machine" not in st.detail


def test_unreachable_server_backs_off_then_retries(monkeypatch):
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, UNREACHABLE)
    calls = []
    real = health.probe_remote

    def counting(url, *a, **kw):
        calls.append(url)
        return real(url, *a, **kw)
    monkeypatch.setattr(health, "probe_remote", counting)

    assert rules_grammar.get_tool() is None
    assert rules_grammar.get_tool() is None          # inside the back-off
    assert len(calls) == 1
    monkeypatch.setattr(rules_grammar, "REMOTE_RETRY_S", 0.0)
    assert rules_grammar.get_tool() is None          # back-off over: retried
    assert len(calls) == 2


def test_sidecar_that_comes_up_later_is_picked_up(fake_lt, monkeypatch):
    """The sidecar often starts after the engine (Cloud Run, compose)."""
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, UNREACHABLE)
    assert rules_grammar.get_tool() is None
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, fake_lt)  # now reachable
    monkeypatch.setattr(rules_grammar, "REMOTE_RETRY_S", 0.0)
    assert rules_grammar.get_tool() is not None
    assert rules_grammar.state()[0] == "ready"


def test_failed_check_never_copies_server_text_into_health(fake_lt,
                                                           monkeypatch):
    from researchly.api import analyze
    _FakeLT.mode = "broken_check"
    a = analyze(f"The {CANARY} values are high.", cfg=Config())
    assert not any(s.rule_id == "LT001" for s in a.suggestions)
    st = _grammar(a.health)
    assert not st.ok and st.state == "error"
    assert CANARY not in st.detail and CANARY not in st.remedy
    assert CANARY not in rules_grammar.state()[1]
    assert "check failed" in st.detail


def test_grammar_recovers_after_the_server_comes_back(fake_lt, monkeypatch):
    from researchly.api import analyze
    monkeypatch.setattr(rules_grammar, "REMOTE_RETRY_S", 0.0)
    _FakeLT.mode = "broken_check"
    analyze("These results are robust.", cfg=Config())
    assert rules_grammar.state()[0] == "error"
    _FakeLT.mode = "ok"
    a = analyze("These results are robust.", cfg=Config())
    assert rules_grammar.state() == ("ready", "")
    assert _grammar(a.health).ok
    assert any(s.rule_id == "LT001" for s in a.suggestions)


def test_grammar_disabled_in_settings_wins_over_remote(fake_lt):
    st = _grammar(health.engine_status(Config(grammar_tier=False)))
    assert st.state == "disabled" and not st.ok


# --- truthful wording: desktop vs hosted ------------------------------------

def test_desktop_wording_is_unchanged():
    rules_grammar._STATE = "ready"
    st = _grammar(health.engine_status(Config()))
    assert st.detail == "local LanguageTool (nothing leaves this machine)"
    sp = next(s for s in health.engine_status(Config())
              if s.tier == "spelling")
    assert "your dictionary" in sp.detail


def test_service_mode_never_claims_nothing_leaves_this_machine(monkeypatch):
    monkeypatch.setenv(health.MODE_ENV, "service")
    rules_grammar._STATE = "ready"
    statuses = health.engine_status(Config())
    for s in statuses:
        assert "nothing leaves this machine" not in s.detail
        assert "this machine" not in s.detail
    st = _grammar(statuses)
    assert st.ok and "never stored" in st.detail
    sp = next(s for s in statuses if s.tier == "spelling")
    assert "your dictionary" not in sp.detail   # no per-user dictionary in S1


def test_service_mode_remote_wording(fake_lt, monkeypatch):
    monkeypatch.setenv(health.MODE_ENV, "service")
    st = _grammar(health.engine_status(Config(), probe=True))
    assert st.ok and "sidecar" in st.detail and "never stored" in st.detail
    assert "this machine" not in st.detail


def test_service_mode_no_java_remedy_points_at_the_sidecar(monkeypatch):
    monkeypatch.setenv(health.MODE_ENV, "service")
    rules_grammar._STATE = "no_java"
    st = _grammar(health.engine_status(Config()))
    assert not st.ok and "RESEARCHLY_LT_URL" in st.remedy
    assert "brew" not in st.remedy


def test_service_mode_gec_wording(monkeypatch):
    from researchly import gec

    class _Fake(gec.EditBackend):
        version = "fake-1"

        def predict(self, text):
            return []
    gec.set_backend(_Fake())
    try:
        monkeypatch.setenv(health.MODE_ENV, "service")
        st = next(s for s in health.engine_status(Config(gec_tier=True))
                  if s.tier == "gec")
        assert st.ok and "this machine" not in st.detail
        monkeypatch.delenv(health.MODE_ENV)
        st = next(s for s in health.engine_status(Config(gec_tier=True))
                  if s.tier == "gec")
        assert "nothing leaves this machine" in st.detail
    finally:
        gec.set_backend(None)


# --- optional: a real LanguageTool server -----------------------------------

REAL = os.environ.get("RESEARCHLY_TEST_LT_URL")


@pytest.mark.skipif(not REAL, reason="set RESEARCHLY_TEST_LT_URL to run "
                                     "against a real LanguageTool server")
def test_real_languagetool_server(monkeypatch):
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, REAL)
    _no_java(monkeypatch)
    from researchly.api import analyze
    a = analyze("We used a infectious disease model.", cfg=Config())
    assert _grammar(a.health).ok, _grammar(a.health)
    assert any(s.rule_id == "LT001" for s in a.suggestions)


# --- the remote path's two S1 code-review findings ------------------------

def test_hung_server_costs_one_timeout_budget_not_two(fake_lt, monkeypatch):
    """language_tool_python retries a timed-out check once, so a per-try
    timeout of REMOTE_TIMEOUT_S really cost twice that while the engine lock
    was held. REMOTE_TIMEOUT_S is now the total budget across both tries."""
    import time
    _no_java(monkeypatch)
    monkeypatch.setattr(rules_grammar, "REMOTE_TIMEOUT_S", 1.0)
    _FakeLT.mode, _FakeLT.hang_s = "hang", 5.0
    from researchly.api import analyze
    t0 = time.monotonic()
    a = analyze("These results are robust.", cfg=Config())
    elapsed = time.monotonic() - t0
    assert not [s for s in a.suggestions if s.rule_id == "LT001"]
    assert elapsed < 1.6, f"grammar held the request for {elapsed:.1f}s"


def test_server_under_a_path_is_used_by_probe_and_client_alike(monkeypatch):
    """RESEARCHLY_LT_URL=http://host/lt: the probe checked /lt/v2/check while
    the client called /v2/check, so health said ready and every check failed."""
    _FakeLT.mode, _FakeLT.checks, _FakeLT.probes = "ok", 0, 0
    _FakeLT.prefix, _FakeLT.hang_s = "/lt", 0.0
    server = HTTPServer(("127.0.0.1", 0), _FakeLT)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv(rules_grammar.REMOTE_ENV,
                           f"http://127.0.0.1:{server.server_address[1]}/lt")
        _no_java(monkeypatch)
        from researchly.api import analyze
        a = analyze("These results are robust.", cfg=Config())
        assert _grammar(a.health).ok
        assert [s for s in a.suggestions if s.rule_id == "LT001"]
        assert _FakeLT.checks == 1
    finally:
        server.shutdown()
        server.server_close()
        _FakeLT.prefix = ""


def test_url_without_scheme_is_accepted_consistently(fake_lt, monkeypatch):
    """`localhost:8010` was accepted by the client but always failed the
    probe, so grammar never started. Both now see the same normalised URL."""
    _no_java(monkeypatch)
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, fake_lt.replace("http://", ""))
    assert rules_grammar.remote_url() == fake_lt
    from researchly.api import analyze
    a = analyze("These results are robust.", cfg=Config())
    assert _grammar(a.health).ok
    assert [s for s in a.suggestions if s.rule_id == "LT001"]
