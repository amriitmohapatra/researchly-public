"""Per-IP rate limit (S1 has no accounts) and CORS (browser origins)."""

from __future__ import annotations

import pytest

from researchly_service import settings as settings_mod
from researchly_service.middleware import RateLimiter, client_ip
from researchly_service.schemas import ErrorResponse

# --- rate limit -------------------------------------------------------------


def test_rate_limiter_window():
    rl = RateLimiter(3, window_s=60)
    assert [rl.check("a", now=t) for t in (0, 1, 2)] == [None] * 3
    wait = rl.check("a", now=3)
    assert wait is not None and 1 <= wait <= 60
    assert rl.check("b", now=3) is None              # per key
    assert rl.check("a", now=61) is None             # window slid


def test_rate_limiter_disabled_and_bounded():
    assert RateLimiter(0).check("a") is None
    rl = RateLimiter(1, max_keys=10)
    for i in range(50):
        rl.check(f"ip{i}", now=float(i * 100))       # all stale by next
    assert len(rl._hits) <= 10


def test_429_after_the_limit(make_client):
    c = make_client(rate_limit_per_min=3)
    codes = [c.get("/v1/rules").status_code for _ in range(3)]
    assert codes == [200, 200, 200]
    r = c.post("/v1/analyze", json={"content": "Text."})
    assert r.status_code == 429
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert body.error.request_id == r.headers["x-request-id"]


def test_health_is_not_rate_limited(make_client):
    c = make_client(rate_limit_per_min=1)
    assert all(c.get("/v1/health").status_code == 200 for _ in range(4))


def test_forwarded_for_with_trusted_hops(make_client):
    c = make_client(rate_limit_per_min=1, trusted_proxy_hops=1)
    a = {"x-forwarded-for": "203.0.113.7"}
    b = {"x-forwarded-for": "198.51.100.9"}
    assert c.get("/v1/rules", headers=a).status_code == 200
    assert c.get("/v1/rules", headers=a).status_code == 429
    assert c.get("/v1/rules", headers=b).status_code == 200
    # A client forging an extra entry on the LEFT is still counted by the
    # entry the trusted proxy appended.
    forged = {"x-forwarded-for": "1.2.3.4, 203.0.113.7"}
    assert c.get("/v1/rules", headers=forged).status_code == 429


def test_forwarded_for_ignored_without_trusted_hops():
    scope = {"headers": [(b"x-forwarded-for", b"9.9.9.9")],
             "client": ("10.1.1.1", 5)}
    assert client_ip(scope, 0) == "10.1.1.1"
    assert client_ip(scope, 1) == "9.9.9.9"
    assert client_ip({"headers": [], "client": None}, 1) == "unknown"


# --- CORS ---------------------------------------------------------------------

APP_ORIGIN = "https://app.researchly.example"


def _preflight(c, origin, method="POST", headers="content-type"):
    return c.options("/v1/analyze", headers={
        "origin": origin, "access-control-request-method": method,
        "access-control-request-headers": headers})


def test_allowed_origin_preflight_and_response(make_client):
    c = make_client(allowed_origins=[APP_ORIGIN])
    p = _preflight(c, APP_ORIGIN)
    assert p.status_code == 200
    assert p.headers["access-control-allow-origin"] == APP_ORIGIN
    allowed = p.headers["access-control-allow-methods"]
    assert "POST" in allowed and "GET" in allowed and "PUT" not in allowed
    r = c.post("/v1/analyze", json={"content": "Text."},
               headers={"origin": APP_ORIGIN})
    assert r.headers["access-control-allow-origin"] == APP_ORIGIN
    assert "x-request-id" in r.headers["access-control-expose-headers"].lower()
    assert "access-control-allow-credentials" not in r.headers


def test_other_origins_methods_and_headers_refused(make_client):
    c = make_client(allowed_origins=[APP_ORIGIN])
    assert "access-control-allow-origin" not in _preflight(
        c, "https://evil.example").headers
    assert _preflight(c, APP_ORIGIN, method="PUT").status_code == 400
    assert _preflight(c, APP_ORIGIN,
                      headers="x-not-ours").status_code == 400
    # S2: the bearer token and the upload headers are allowed (no cookies:
    # credentials stay off).
    ok = _preflight(c, APP_ORIGIN, headers="authorization,x-researchly-filename,"
                                           "x-researchly-options")
    assert ok.status_code == 200
    assert "access-control-allow-credentials" not in ok.headers
    r = c.get("/v1/rules", headers={"origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_error_responses_carry_cors_headers(make_client):
    """A browser can only read a 413/429 body if CORS headers are on it."""
    c = make_client(allowed_origins=[APP_ORIGIN], rate_limit_per_min=1,
                    max_body_bytes=1024)
    r = c.post("/v1/analyze", json={"content": "x" * 5000},
               headers={"origin": APP_ORIGIN})
    assert r.status_code == 413
    assert r.headers["access-control-allow-origin"] == APP_ORIGIN
    r = c.get("/v1/rules", headers={"origin": APP_ORIGIN})
    assert r.status_code == 429
    assert r.headers["access-control-allow-origin"] == APP_ORIGIN
    exposed = r.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed and "x-request-id" in exposed
    assert int(r.headers["retry-after"]) >= 1


@pytest.mark.parametrize("env,raw,expected", [
    ({}, None, []),                                       # prod: none
    ({"RESEARCHLY_ENV": "development"}, None, settings_mod.DEV_ORIGINS),
    ({}, "https://a.example, https://b.example/",
     ["https://a.example", "https://b.example"]),
    ({}, "*", []),                                        # wildcard refused
    ({"RESEARCHLY_ENV": "development"}, "https://a.example",
     ["https://a.example"]),                              # explicit wins
])
def test_allowed_origins_from_env(monkeypatch, env, raw, expected):
    monkeypatch.delenv("RESEARCHLY_ENV", raising=False)
    monkeypatch.delenv("RESEARCHLY_ALLOWED_ORIGINS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if raw is not None:
        monkeypatch.setenv("RESEARCHLY_ALLOWED_ORIGINS", raw)
    assert settings_mod.load().allowed_origins == expected
