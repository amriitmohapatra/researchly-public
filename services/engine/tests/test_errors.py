"""Every error is an ErrorResponse with a request id, and the size cap is
enforced before the body is read."""

from __future__ import annotations

import asyncio
import json

from researchly_service import engine_adapter
from researchly_service.middleware import RateLimiter, RequestContextMiddleware
from researchly_service.schemas import MAX_CONTENT_CHARS, ErrorResponse

from conftest import make_settings


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = ErrorResponse.model_validate(resp.json())      # extra=forbid
    assert body.error.code == code
    assert body.error.message
    assert body.error.request_id == resp.headers["x-request-id"]
    return body


def test_validation_error_422(client):
    r = client.post("/v1/analyze", json={"content": ""})
    assert_error(r, 422, "invalid_request")
    r = client.post("/v1/analyze", json={"format": "docx", "content": "x"})
    b = assert_error(r, 422, "invalid_request")
    assert "plain" in b.error.message                 # schema's choices
    r = client.post("/v1/analyze", json={})
    assert "required" in assert_error(r, 422, "invalid_request").error.message


def test_too_many_disabled_rules_422(client):
    r = client.post("/v1/analyze", json={
        "content": "x", "options": {"disabled_rules": ["G101"] * 201}})
    assert "too many" in assert_error(r, 422, "invalid_request").error.message


def test_content_over_the_character_cap_422(client):
    r = client.post("/v1/analyze",
                    json={"content": "a" * (MAX_CONTENT_CHARS + 1)})
    b = assert_error(r, 422, "invalid_request")
    assert str(MAX_CONTENT_CHARS) in b.error.message


def test_malformed_json_400(client):
    r = client.post("/v1/analyze", content=b'{"content": "unterminated',
                    headers={"content-type": "application/json"})
    assert_error(r, 400, "malformed_json")


def test_non_json_body_is_rejected(client):
    r = client.post("/v1/analyze", content=b"plain words",
                    headers={"content-type": "text/plain"})
    assert r.status_code in (400, 415, 422)
    ErrorResponse.model_validate(r.json())


def test_not_found_and_method_not_allowed(client):
    assert_error(client.get("/v1/nothing-here"), 404, "not_found")
    assert_error(client.get("/v1/analyze"), 405, "method_not_allowed")


def test_oversized_body_413(make_client):
    c = make_client(max_body_bytes=2048)
    r = c.post("/v1/analyze", json={"content": "word " * 1000})
    assert_error(r, 413, "payload_too_large")


def test_oversized_chunked_body_413(make_client):
    c = make_client(max_body_bytes=2048)

    def gen():
        yield b'{"content": "'
        for _ in range(100):
            yield b"word " * 20
        yield b'"}'
    r = c.post("/v1/analyze", content=gen(),
               headers={"content-type": "application/json"})
    assert_error(r, 413, "payload_too_large")


def test_chunked_body_under_the_cap_is_served(make_client):
    c = make_client(max_body_bytes=1024 * 1024)

    def gen():
        yield b'{"content": "'
        yield b"Results were consistent across districts."
        yield b'"}'
    r = c.post("/v1/analyze", content=gen(),
               headers={"content-type": "application/json"})
    assert r.status_code == 200, r.text


def test_413_is_decided_before_the_body_is_read():
    """Drive the middleware directly: a declared Content-Length over the cap
    is refused without a single receive() call."""
    reached = {"app": False, "receive": False}

    async def app(scope, receive, send):
        reached["app"] = True

    async def receive():
        reached["receive"] = True
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    mw = RequestContextMiddleware(app, make_settings(max_body_bytes=1000),
                                  RateLimiter(0))
    scope = {"type": "http", "method": "POST", "path": "/v1/analyze",
             "headers": [(b"content-length", b"999999999"),
                         (b"content-type", b"application/json")],
             "client": ("10.0.0.1", 1234)}
    asyncio.run(mw(scope, receive, send))
    assert not reached["app"] and not reached["receive"]
    assert sent[0]["status"] == 413
    body = json.loads(sent[1]["body"])
    assert body["error"]["code"] == "payload_too_large"
    assert (b"x-request-id", body["error"]["request_id"].encode()) in \
        sent[0]["headers"]


def test_bad_content_length_400():
    async def app(scope, receive, send):
        raise AssertionError("must not reach the app")

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    mw = RequestContextMiddleware(app, make_settings(), RateLimiter(0))
    scope = {"type": "http", "method": "POST", "path": "/v1/analyze",
             "headers": [(b"content-length", b"lots")], "client": None}
    asyncio.run(mw(scope, receive, send))
    assert sent[0]["status"] == 400


def test_internal_error_500(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(engine_adapter.api, "analyze", boom)
    r = client.post("/v1/analyze", json={"content": "Some text."})
    b = assert_error(r, 500, "internal")
    assert "engine exploded" not in r.text
    assert "Nothing was stored" in b.error.message


def test_request_ids_are_unique(client):
    ids = {client.get("/v1/rules").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


def test_client_supplied_request_id_is_not_trusted(client):
    r = client.get("/v1/rules", headers={"x-request-id": "evil\nlog-line"})
    assert r.headers["x-request-id"] != "evil\nlog-line"


def test_body_cap_admits_any_valid_document():
    """Every document the contract accepts must fit under the body cap, or a
    valid 1M-character text in a 4-byte script is refused with 413 before the
    content check can explain the real limit (S1 review finding)."""
    from researchly_service.schemas import MAX_CONTENT_CHARS
    from researchly_service.settings import Settings, load
    worst_case = MAX_CONTENT_CHARS * 4 + 64 * 1024   # 4-byte chars + envelope
    assert Settings().max_body_bytes >= worst_case
    assert load().max_body_bytes >= worst_case


def test_documented_error_codes_match_what_the_service_emits():
    """The contract lists the error codes; a new one must be documented."""
    import re
    from pathlib import Path
    from researchly_service.schemas import ErrorBody
    documented = set(re.findall(r"[a-z_]{4,}", ErrorBody.model_fields["code"].description))
    src = Path(__file__).resolve().parents[1] / "researchly_service"
    emitted = set()
    for name in ("errors.py", "middleware.py"):
        text = (src / name).read_text()
        # every way a code is written: a status table (`413: "x"`), a
        # helper call (`_respond(request, 413, "x"`, `reply_error(413, "x"`)
        # and the fallback (`STATUS_CODES.get(status, "x")`).
        emitted |= set(re.findall(r'\b\d{3}\s*[:,]\s*"([a-z_]+)"', text))
        emitted |= set(re.findall(r'\.get\(\s*status\s*,\s*"([a-z_]+)"', text))
    assert {"payload_too_large", "malformed_json", "internal"} <= emitted, \
        "the patterns no longer find the codes; update this test"
    assert emitted <= documented, sorted(emitted - documented)
