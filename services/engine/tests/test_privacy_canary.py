"""Q6 canary suite — RELEASE-BLOCKING (ARCHITECTURE.md §3 Q6, ADR-02).

Claim: document text never appears in logs or error bodies.

Design. Every scenario posts a document carrying a unique canary string and
then searches EVERYTHING that could persist or leave the request:

1. every LogRecord emitted by any logger (root, uvicorn.*, researchly.*,
   third-party), captured at DEBUG via caplog — checked raw: the rendered
   message, every attribute on the record, and any attached exception's
   message. This is stricter than checking formatted output: a record that
   merely *carries* the canary fails, whatever a formatter would print;
2. the production JSON formatter's actual output (a handler with
   logging_setup.JsonFormatter on the root logger);
3. the process's stdout and stderr at the file-descriptor level (capfd), so
   a stray print() or a child process's output would be caught too;
4. every error response body and header.

The success response MAY contain the canary in suggestion `text` — that is
the user's own document going back to them — but its `health` block must not
(health details are also served on the public /v1/health).

The harness proves it can see a leak (test_harness_detects_a_leak), so a
green run means "looked and found nothing", not "could not look".

Found by this suite and fixed (2026-10-03): when a log handler failed to
write (a closed stdout), `logging.Handler.handleError` printed a traceback to
stderr that chained the original engine exception — document and all —
because the error net logged inside its `except` block. Now the net logs
after the block, the JSON handler never dumps tracebacks, and
`logging.raiseExceptions` is off (test_broken_log_handler_never_dumps_text).

Scenarios: successful analysis · validation errors (bad enum value, unknown
field named with the canary, content over the character cap, list too long)
· malformed JSON · oversized body (declared and chunked) · a forced internal
error whose message IS the document, raised both by a monkeypatched
api.analyze and by a real rule inside the real engine · a grammar backend
whose failure message echoes the text · canaries in the query string and
the path.
"""

from __future__ import annotations

import io
import logging

import pytest

from researchly import rules_grammar
from researchly.engine import REGISTRY

from researchly_service import engine_adapter, logging_setup

from conftest import make_settings  # noqa: F401

CANARY = "CANARY-7f3a9c"
DOC = (f"Discussion\n\nThe {CANARY} model was calibrated by the authors. "
       f"This are very clear {CANARY} results.\n")


# Loggers of the TEST CLIENT, which runs in this process but is the caller,
# not the service: httpx logs the URL it requested, query string included.
CLIENT_SIDE = ("httpx", "httpcore")


@pytest.fixture
def capture(caplog, capfd):
    """All log records (DEBUG, every logger) + JSON output + fd 1/2."""
    caplog.set_level(logging.DEBUG)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access",
                 "language_tool_python", "researchly", "starlette",
                 "fastapi"):
        caplog.set_level(logging.DEBUG, logger=name)
    # Silence the in-process TEST CLIENT (the caller, not the service): httpx
    # logs each URL it requests, query string included, through the same
    # root handlers the service uses.
    # (Not caplog.set_level: that also raises caplog's own handler level.)
    saved_levels = {n: logging.getLogger(n).level for n in CLIENT_SIDE}
    for name in CLIENT_SIDE:
        logging.getLogger(name).setLevel(logging.WARNING)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging_setup.JsonFormatter())
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)

    class Captured:
        def records(self):
            return list(caplog.records)

        def json_lines(self):
            return buf.getvalue()

        def fds(self):
            out, err = capfd.readouterr()
            self._fd = getattr(self, "_fd", "") + out + err
            return self._fd

    yield Captured()
    root.removeHandler(handler)
    for name, level in saved_levels.items():
        logging.getLogger(name).setLevel(level)


def _record_strings(rec: logging.LogRecord):
    try:
        yield rec.getMessage()
    except Exception:
        yield str(rec.msg)
    for k, v in rec.__dict__.items():
        if k in ("exc_info",):
            continue
        yield f"{k}={v!r}"
    if rec.exc_info and rec.exc_info[1] is not None:
        yield repr(rec.exc_info[1])
        yield str(rec.exc_info[1])
    if rec.exc_text:
        yield rec.exc_text


def assert_no_canary_anywhere(cap, *responses):
    for rec in cap.records():
        if rec.name.split(".")[0] in CLIENT_SIDE:
            continue
        for s in _record_strings(rec):
            assert CANARY not in s, \
                f"canary in a log record from {rec.name}: {s[:200]}"
    assert CANARY not in cap.json_lines(), "canary in JSON log output"
    assert CANARY not in cap.fds(), "canary on stdout/stderr"
    for r in responses:
        for k, v in r.headers.items():
            assert CANARY not in v, f"canary in response header {k}"
        if r.status_code >= 400:
            assert CANARY not in r.text, \
                f"canary in a {r.status_code} error body"


def assert_logged_request(cap, status):
    lines = [r for r in cap.records()
             if r.name == "researchly.access" and getattr(r, "status", None)
             == status]
    assert lines, f"no access-log line for status {status}"
    return lines[-1]


# --- the harness can see a leak -------------------------------------------

def test_harness_detects_a_leak(capture):
    logging.getLogger("researchly.service").warning("leak %s", CANARY)
    print(CANARY)
    with pytest.raises(AssertionError):
        assert_no_canary_anywhere(capture)


# --- scenarios ---------------------------------------------------------------

def test_successful_analysis(client, capture):
    r = client.post("/v1/analyze", json={"content": DOC})
    assert r.status_code == 200
    body = r.json()
    # The user's own text may come back in suggestions, but never in the
    # health block (also served publicly).
    for t in body["health"]:
        assert CANARY not in t["detail"] and CANARY not in t["remedy"]
    rec = assert_logged_request(capture, 200)
    assert rec.content_chars == len(DOC) and rec.format == "plain"
    assert rec.suggestions == len(body["suggestions"])
    assert_no_canary_anywhere(capture, r)


@pytest.mark.parametrize("payload", [
    {"format": CANARY, "content": DOC},                         # bad enum
    {"content": DOC, CANARY: 1},                                # unknown key
    {"content": DOC, "options": {CANARY: True}},                # nested key
    {"content": DOC, "options": {"disabled_rules": [CANARY] * 201}},
    {"content": DOC, "options": {"show_preferences": CANARY}},  # bad bool
    {"content": [DOC]},                                         # wrong type
])
def test_validation_errors(client, capture, payload):
    r = client.post("/v1/analyze", json=payload)
    assert r.status_code == 422
    assert_logged_request(capture, 422)
    assert_no_canary_anywhere(capture, r)


def test_content_over_the_character_cap(client, capture):
    from researchly_service.schemas import MAX_CONTENT_CHARS
    big = (DOC * (MAX_CONTENT_CHARS // len(DOC) + 2))
    assert len(big) > MAX_CONTENT_CHARS
    r = client.post("/v1/analyze", json={"content": big})
    assert r.status_code == 422
    assert_no_canary_anywhere(capture, r)


def test_malformed_json(client, capture):
    raw = ('{"content": "' + DOC.replace("\n", " ") + '", ').encode()
    r = client.post("/v1/analyze", content=raw,
                    headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert_no_canary_anywhere(capture, r)


def test_oversized_request(client, capture):
    big = DOC * (5 * 1024 * 1024 // len(DOC) + 1)               # > 4 MiB
    r = client.post("/v1/analyze", json={"content": big})
    assert r.status_code == 413
    assert_logged_request(capture, 413)
    assert_no_canary_anywhere(capture, r)


def test_oversized_chunked_request(make_client, capture):
    c = make_client(max_body_bytes=4096)

    def gen():
        yield b'{"content": "'
        for _ in range(50):
            yield DOC.replace("\n", " ").encode()
        yield b'"}'
    r = c.post("/v1/analyze", content=gen(),
               headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert_no_canary_anywhere(capture, r)


def test_forced_internal_error_from_analyze(client, capture, monkeypatch):
    def boom(source, *a, **kw):
        raise RuntimeError(f"engine failed on: {source}")    # message = doc
    monkeypatch.setattr(engine_adapter.api, "analyze", boom)
    r = client.post("/v1/analyze", json={"content": DOC})
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"
    errs = [x for x in capture.records()
            if getattr(x, "event", None) == "unhandled_exception"]
    assert errs and errs[-1].error_type == "RuntimeError"
    assert errs[-1].request_id == r.headers["x-request-id"]
    assert_no_canary_anywhere(capture, r)


def test_forced_internal_error_inside_a_real_rule(client, capture,
                                                  monkeypatch):
    """The real engine path: a rule raises with the document in its message,
    and the exception carries frames whose locals hold the text."""
    rule = REGISTRY["G104"]

    def exploding_rule(doc, document):
        text = document.original                       # a local holding it
        raise ValueError(f"cannot parse {text}")
        yield                                          # pragma: no cover
    monkeypatch.setattr(rule, "func", exploding_rule)
    r = client.post("/v1/analyze", json={"content": DOC})
    assert r.status_code == 500
    assert_no_canary_anywhere(capture, r)


def test_grammar_failure_that_echoes_text(client, capture, monkeypatch):
    """A grammar backend whose error message quotes the document must not
    put it in health — which the PUBLIC /v1/health also serves."""
    class EchoingTool:
        def check(self, text):
            raise RuntimeError(f"LanguageTool choked on: {text}")

        def close(self):
            pass

    monkeypatch.delenv(rules_grammar.REMOTE_ENV, raising=False)
    for k, v in (("_TOOL", EchoingTool()), ("_LOCALE", "en-US"),
                 ("_URL", None), ("_FAILED", False), ("_STATE", "ready"),
                 ("_DETAIL", "")):
        monkeypatch.setattr(rules_grammar, k, v)
    r = client.post("/v1/analyze", json={"content": DOC})
    assert r.status_code == 200
    for t in r.json()["health"]:
        assert CANARY not in t["detail"] + t["remedy"]
    h = client.get("/v1/health")
    assert CANARY not in h.text
    assert_no_canary_anywhere(capture, r, h)


def test_canary_in_query_string_and_path(client, capture):
    r1 = client.get(f"/v1/health?q={CANARY}")
    r2 = client.get(f"/v1/{CANARY}")
    r3 = client.post(f"/v1/analyze?{CANARY}=1", json={"content": "Fine."})
    assert r2.status_code == 404
    assert_no_canary_anywhere(capture, r1, r2, r3)
    routes = {getattr(x, "route", None) for x in capture.records()
              if x.name == "researchly.access"}
    assert "other" in routes


def test_access_log_carries_only_the_allowed_fields(client, capture):
    client.post("/v1/analyze", json={"content": DOC})
    rec = assert_logged_request(capture, 200)
    allowed = set(logging_setup.ALLOWED_FIELDS)
    std = set(logging.LogRecord("x", 0, "", 0, "", None, None).__dict__) | {
        "message", "asctime", "taskName"}
    custom = set(rec.__dict__) - std
    assert custom <= allowed, custom - allowed


def test_broken_log_handler_never_dumps_text(client, capture, monkeypatch):
    """Regression: a handler that cannot write must not make Python print
    the in-flight exception (which quotes the document) to stderr — even if
    some library turns logging.raiseExceptions back on."""
    class Broken(logging.StreamHandler):
        """Fails the way StreamHandler does on a closed stream: emit()
        catches the error and calls the stock handleError()."""
        def emit(self, record):
            try:
                raise ValueError("I/O operation on closed file")
            except Exception:
                self.handleError(record)
    broken = Broken()
    root = logging.getLogger()
    root.addHandler(broken)
    monkeypatch.setattr(logging, "raiseExceptions", True)

    def boom(source, *a, **kw):
        raise RuntimeError(f"engine failed on: {source}")
    monkeypatch.setattr(engine_adapter.api, "analyze", boom)
    try:
        r = client.post("/v1/analyze", json={"content": DOC})
    finally:
        root.removeHandler(broken)
    assert r.status_code == 500
    assert_no_canary_anywhere(capture, r)


# --- S2: uploads and accounts -------------------------------------------------

def test_upload_canary_in_content_filename_and_options(client, capture):
    """A filename can be confidential ("trial_X_unblinded.docx"): it is
    echoed to the caller but must never reach a log."""
    import json as _json
    import urllib.parse as _up
    headers = {"content-type": "application/octet-stream",
               "x-researchly-filename": _up.quote(f"{CANARY}_chapter.md"),
               "x-researchly-options": _json.dumps({"show_preferences": True})}
    r = client.post("/v1/analyze-file", content=DOC.encode(), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["document"]["filename"] == f"{CANARY}_chapter.md"
    rec = assert_logged_request(capture, 200)
    assert rec.upload_bytes == len(DOC.encode()) and rec.format == "markdown"
    # Error paths with the canary in the filename and the options.
    bad = [dict(headers, **{"x-researchly-filename": _up.quote(f"{CANARY}.pdf")}),
           dict(headers, **{"x-researchly-options": _json.dumps({CANARY: 1})}),
           dict(headers, **{"x-researchly-options": "{" + CANARY})]
    responses = [client.post("/v1/analyze-file", content=DOC.encode(), headers=h)
                 for h in bad]
    assert [x.status_code for x in responses] == [415, 422, 422]
    # The success body legitimately echoes the filename and text back.
    assert_no_canary_anywhere(capture, *responses)
    for k, v in r.headers.items():
        assert CANARY not in v


def test_token_and_user_id_never_logged(make_client, capture):
    """The bearer token and the user id are identifying: neither is logged,
    on success or on refusal."""
    import test_accounts as ta
    c = make_client(supabase_url=ta.URL, supabase_publishable_key=ta.PUBLISHABLE)
    fake = ta.FakeSupabase({"show_preferences": True})
    c.app.state.accounts = ta.accounts.Accounts(
        ta.URL, ta.PUBLISHABLE, jwks_client=ta.InMemoryJWKS(), fetch=fake)
    good = ta.token(email=f"{CANARY}@example.org")
    expired = ta.token(exp=1, iat=0)
    r1 = c.post("/v1/analyze", json={"content": DOC},
                headers={"authorization": f"Bearer {good}"})
    r2 = c.post("/v1/analyze", json={"content": DOC},
                headers={"authorization": f"Bearer {expired}"})
    assert (r1.status_code, r2.status_code) == (200, 401)
    rec = assert_logged_request(capture, 200)
    assert rec.signed_in is True
    for secret in (good, expired, ta.USER, CANARY):
        for x in capture.records():
            if x.name.split(".")[0] in CLIENT_SIDE:
                continue
            for s in _record_strings(x):
                assert secret not in s, f"{secret[:12]}… in a log record"
        assert secret not in capture.json_lines()
        assert secret not in capture.fds()
        assert secret not in r2.text


def test_upload_warnings_never_logged(client, capture):
    """Adapter warnings can quote document text (an \\input target's name):
    returned to the caller, never logged."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / "packages/core/tests"))
    from ingest_fixtures import zip_bytes
    main = ("\\documentclass{article}\n\\begin{document}\n"
            f"Text.\n\\input{{{CANARY}}}\n\\end{{document}}\n")
    r = client.post("/v1/analyze-file", content=zip_bytes({"main.tex": main}),
                    headers={"content-type": "application/octet-stream",
                             "x-researchly-filename": "p.zip"})
    assert r.status_code == 200, r.text
    assert any(CANARY in w for w in r.json()["document"]["warnings"])
    assert_no_canary_anywhere(capture)
