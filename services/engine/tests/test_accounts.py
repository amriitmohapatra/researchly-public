"""Accounts (S2): who is asking, and do their settings apply? (s2-design §3)

Tokens are minted here with throwaway keys and checked by the real
verification path: a real PyJWKClient whose key-set download is replaced by
an in-memory JWKS, so key-id lookup, algorithm pinning and every claim check
run exactly as in production. Supabase's settings RPC is a fake that records
what the engine sent.
"""

from __future__ import annotations

import json
import time
import urllib.error
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from researchly_service import accounts

from conftest import PREFERENCE_TEXT

URL = "https://abcdefghijklmnop.supabase.co"
ISSUER = URL + "/auth/v1"
PUBLISHABLE = "sb_publishable_test_only"
USER = str(uuid.uuid4())

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EC_KEY = ec.generate_private_key(ec.SECP256R1())
STRANGER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private, kid, alg):
    pub = private.public_key()
    algo = jwt.algorithms.RSAAlgorithm if alg == "RS256" else jwt.algorithms.ECAlgorithm
    d = json.loads(algo.to_jwk(pub))
    d.update(kid=kid, alg=alg, use="sig")
    return d


JWKS = {"keys": [_jwk(RSA_KEY, "rsa-1", "RS256"), _jwk(EC_KEY, "ec-1", "ES256")]}


class InMemoryJWKS(jwt.PyJWKClient):
    """The real client, minus the network."""

    def __init__(self, jwks=JWKS, down=False):
        super().__init__(ISSUER + "/.well-known/jwks.json", cache_keys=True)
        self._data, self._down = jwks, down

    def fetch_data(self):
        if self._down:
            raise jwt.PyJWKClientConnectionError("unreachable")
        return self._data


def token(key=RSA_KEY, kid="rsa-1", alg="RS256", **over):
    now = int(time.time())
    claims = {"sub": USER, "aud": "authenticated", "role": "authenticated",
              "iss": ISSUER, "iat": now, "exp": now + 3600,
              "email": "student@example.org"}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


class FakeSupabase:
    def __init__(self, settings=None, error=None):
        self.settings = settings if settings is not None else {}
        self.error = error
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        if self.error is not None:
            raise self.error
        return self.settings


@pytest.fixture
def signed(make_client):
    """A client with accounts on; returns (client, fake supabase)."""
    def _make(settings=None, error=None, jwks_down=False, **kw):
        c = make_client(supabase_url=URL, supabase_publishable_key=PUBLISHABLE,
                        **kw)
        fake = FakeSupabase(settings, error)
        c.app.state.accounts = accounts.Accounts(
            URL, PUBLISHABLE, jwks_client=InMemoryJWKS(down=jwks_down), fetch=fake)
        return c, fake
    return _make


def post(c, text=PREFERENCE_TEXT, tok=None, auth=None, **options):
    headers = {}
    if tok is not None:
        headers["authorization"] = f"Bearer {tok}"
    if auth is not None:
        headers["authorization"] = auth
    return c.post("/v1/analyze", json={"content": text, "options": options},
                  headers=headers)


def rules_of(r):
    return {s["rule_id"] for s in r.json()["suggestions"]}


# --- the happy path ---------------------------------------------------------

@pytest.mark.parametrize("kw", [{}, {"key": EC_KEY, "kid": "ec-1", "alg": "ES256"}],
                         ids=["RS256", "ES256"])
def test_signed_in_settings_apply(signed, kw):
    c, fake = signed({"disabled_rules": [], "show_preferences": True,
                      "locale": "en-GB", "dictionary": []})
    r = post(c, tok=token(**kw))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signed_in"] is True
    assert "W204" in rules_of(r)          # stored show_preferences took effect
    account = [t for t in body["health"] if t["tier"] == "account"]
    assert account and account[0]["ok"] is True


def test_settings_are_fetched_with_the_callers_own_token(signed):
    c, fake = signed({})
    tok = token()
    post(c, tok=tok)
    (call,) = fake.calls
    assert call["url"] == URL + "/rest/v1/rpc/my_config"
    assert call["headers"]["Authorization"] == f"Bearer {tok}"
    assert call["headers"]["apikey"] == PUBLISHABLE


def test_a_request_can_add_mutes_but_not_unmute(signed):
    c, _ = signed({"disabled_rules": ["W204"], "show_preferences": True})
    # The stored mute wins even though the request asks for preferences.
    assert "W204" not in rules_of(post(c, tok=token(), show_preferences=True))
    # A request can mute more.
    c2, _ = signed({"show_preferences": True})
    assert "W204" not in rules_of(post(c2, tok=token(), disabled_rules=["W204"]))


def test_stored_dictionary_words_are_not_flagged(signed):
    text = "Results\n\nThe zorblatic estimator converged in every district."
    c, _ = signed({})
    flagged = {s["text"] for s in post(c, text, tok=token()).json()["suggestions"]}
    if "zorblatic" not in flagged:
        pytest.skip("spelling tier not flagging the probe word in this env")
    c2, _ = signed({"dictionary": ["zorblatic"]})
    assert "zorblatic" not in {s["text"] for s in
                               post(c2, text, tok=token()).json()["suggestions"]}


def test_malformed_stored_values_are_dropped_not_trusted(signed):
    c, _ = signed({"disabled_rules": ["W204", "'; drop table", 7],
                   "show_preferences": "yes", "locale": "xx",
                   "dictionary": ["ok", "has space", "x" * 65, None]})
    r = post(c, tok=token())
    assert r.status_code == 200
    assert "W204" not in rules_of(r)       # the valid entry still applied


# --- refusing bad tokens ----------------------------------------------------

BAD_TOKENS = {
    "expired": lambda: token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200),
    "wrong issuer": lambda: token(iss="https://other.supabase.co/auth/v1"),
    "wrong audience": lambda: token(aud="something-else"),
    "anon role": lambda: token(role="anon"),
    "service role": lambda: token(role="service_role"),
    "sub not a uuid": lambda: token(sub="admin"),
    "no sub": lambda: token(sub=None),
    "no exp": lambda: token(exp=None),
    "unknown key id": lambda: token(kid="nope"),
    "signed by a stranger": lambda: token(key=STRANGER_KEY),
    # Algorithm confusion: an HS256 token "signed" with public material.
    "HS256 with the publishable key": lambda: jwt.encode(
        {"sub": USER, "aud": "authenticated", "role": "authenticated",
         "iss": ISSUER, "iat": int(time.time()), "exp": int(time.time()) + 600},
        PUBLISHABLE, algorithm="HS256", headers={"kid": "rsa-1"}),
    "alg none": lambda: jwt.encode(
        {"sub": USER, "aud": "authenticated", "role": "authenticated",
         "iss": ISSUER, "iat": int(time.time()), "exp": int(time.time()) + 600},
        None, algorithm="none", headers={"kid": "rsa-1"}),
    "RSA key, ES256 header": lambda: token(kid="rsa-1", key=EC_KEY, alg="ES256"),
    "garbage": lambda: "not.a.jwt",
}


@pytest.mark.parametrize("name", sorted(BAD_TOKENS))
def test_bad_tokens_are_refused_never_treated_as_anonymous(signed, name):
    c, fake = signed({"show_preferences": True})
    r = post(c, tok=BAD_TOKENS[name]())
    assert r.status_code == 401, (name, r.text)
    assert r.json()["error"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert fake.calls == []                # no settings fetched for a bad token


@pytest.mark.parametrize("header", ["Basic abc", "Bearer", "Bearer ", "token"])
def test_malformed_authorization_header(signed, header):
    c, _ = signed({})
    r = post(c, auth=header)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_keys_unreachable_is_503_not_401(signed):
    c, _ = signed({}, jwks_down=True)
    r = post(c, tok=token())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "auth_unavailable"


@pytest.mark.parametrize("error,kind", [
    (urllib.error.URLError("down"), "unreachable"),
    (TimeoutError(), "unreachable"),
    (urllib.error.HTTPError(URL, 500, "x", {}, None), "http_500"),
    (ValueError("not json"), "bad_response"),
])
def test_settings_failure_degrades_visibly(signed, error, kind):
    c, _ = signed(error=error)
    r = post(c, tok=token())
    assert r.status_code == 200
    body = r.json()
    assert body["signed_in"] is True and body["suggestions"] is not None
    (tier,) = [t for t in body["health"] if t["tier"] == "account"]
    assert tier["ok"] is False and tier["state"] == "error"
    assert kind in tier["detail"] and "defaults" in tier["remedy"]


# --- anonymous use and deployments without accounts -------------------------

def test_anonymous_paste_is_capped_when_accounts_are_on(signed):
    c, _ = signed({}, anon_max_words=10)
    short = "Results\n\nThe effect was large."
    assert post(c, short).status_code == 200
    r = post(c, "word " * 11)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "sign_in_required"
    assert "10" in r.json()["error"]["message"]
    assert post(c, "word " * 11, tok=token()).status_code == 200


def test_without_accounts_tokens_are_ignored_and_nothing_is_capped(make_client):
    c = make_client(anon_max_words=10)
    assert c.app.state.accounts is None
    r = post(c, "Results\n\n" + "The effect was large. " * 20, tok="whatever")
    assert r.status_code == 200
    assert r.json()["signed_in"] is False
    assert all(t["tier"] != "account" for t in r.json()["health"])


def test_caller_repr_hides_the_token():
    assert "eyJ" not in repr(accounts.Caller(user_id=USER, token=token()))


# --- operator settings --------------------------------------------------------

def test_settings_from_environment(monkeypatch):
    from researchly_service import settings as settings_mod
    monkeypatch.setenv("RESEARCHLY_SUPABASE_URL", URL + "/")
    monkeypatch.setenv("RESEARCHLY_SUPABASE_PUBLISHABLE_KEY", PUBLISHABLE)
    s = settings_mod.load()
    assert s.supabase_url == URL and s.accounts_enabled
    assert s.max_upload_bytes == 25 * 1024 * 1024 and s.anon_max_words == 1500


@pytest.mark.parametrize("key", ["sb_secret_abc", "eyJhbGciOiJIUzI1NiJ9.service_role.x"])
def test_engine_refuses_to_start_with_a_secret_key(monkeypatch, key):
    from researchly_service import settings as settings_mod
    monkeypatch.setenv("RESEARCHLY_SUPABASE_URL", URL)
    monkeypatch.setenv("RESEARCHLY_SUPABASE_PUBLISHABLE_KEY", key)
    with pytest.raises(ValueError, match="publishable"):
        settings_mod.load()


@pytest.mark.parametrize("url,ok", [
    ("http://abc.supabase.co", False),            # keys fetched in the clear
    ("ftp://abc.supabase.co", False),
    ("http://localhost:54321", True),             # `supabase start`
    ("https://abc.supabase.co", True),
])
def test_supabase_url_must_be_https(monkeypatch, url, ok):
    from researchly_service import settings as settings_mod
    monkeypatch.setenv("RESEARCHLY_SUPABASE_URL", url)
    monkeypatch.setenv("RESEARCHLY_SUPABASE_PUBLISHABLE_KEY", PUBLISHABLE)
    assert settings_mod.load().accounts_enabled is ok
