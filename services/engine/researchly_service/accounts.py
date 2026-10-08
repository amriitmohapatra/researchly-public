"""Who is asking, and what have they set? (docs/s2-design.md §3)

The browser sends the caller's Supabase access token as
`Authorization: Bearer …`. This module

1. verifies it here, against the project's public signing keys (JWKS):
   signature, issuer, audience, expiry and role. `user_id` comes only from
   the verified `sub`, never from the request body (ARCHITECTURE.md §9);
2. fetches the caller's settings with `rpc/my_config`, sending the caller's
   own token. The engine holds no secret key, so Row-Level Security — not
   this code — decides which rows it can see.

Failures are distinct, because they need different responses:
- the token is wrong                        → 401 unauthorized
- the keys can't be fetched to check it     → 503 auth_unavailable
- the token is fine but settings won't load → the check runs with
  defaults and the `account` health tier says so (no silent tier).

Nothing here logs the token, the user id or the settings.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import jwt

# New Supabase projects sign with asymmetric keys (RS256 by default; ES256
# can be chosen). HS256 is deliberately absent: accepting it would let
# anyone holding the publishable key's sibling secret — or a confused
# algorithm header — mint tokens. Legacy-secret projects must migrate.
ALGORITHMS = ["RS256", "ES256"]
AUDIENCE = "authenticated"
LEEWAY_S = 30                  # clock skew between Supabase and Cloud Run
HTTP_TIMEOUT_S = 3.0
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_TOKEN_CHARS = 8192


class AuthError(Exception):
    """A request the engine must refuse. `message` is user-safe."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


UNAUTHORIZED = ("Your sign-in has expired or is not valid. Sign in again; "
                "your text is still here.")


class SettingsUnavailable(Exception):
    """Settings could not be loaded. `kind` is a short, text-free reason."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class Caller:
    user_id: str
    token: str

    def __repr__(self) -> str:            # never print the token
        return "Caller(<redacted>)"


def bearer_token(header: Optional[str]) -> Optional[str]:
    """The token from an Authorization header; None when there is none.
    A header that is present but not a usable Bearer token is an error, not
    "anonymous": a client that thinks it is signed in must be told."""
    if header is None or not header.strip():
        return None
    scheme, _, token = header.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN_CHARS:
        raise AuthError(401, "unauthorized", UNAUTHORIZED)
    return token


Fetch = Callable[[str, Dict[str, str], bytes, float], Any]


def _http_post_json(url: str, headers: Dict[str, str], body: bytes,
                    timeout: float) -> Any:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1_000_000))


class Accounts:
    """Token verification and settings lookup for one Supabase project."""

    def __init__(self, supabase_url: str, publishable_key: str, *,
                 jwks_client: Optional[jwt.PyJWKClient] = None,
                 fetch: Optional[Fetch] = None):
        self.url = supabase_url.rstrip("/")
        self.issuer = f"{self.url}/auth/v1"
        self.publishable_key = publishable_key
        # PyJWKClient caches the key set and re-fetches when it meets a key
        # id it has not seen (Supabase key rotation).
        self._jwks = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json", cache_keys=True,
            lifespan=600, timeout=HTTP_TIMEOUT_S)
        self._fetch = fetch or _http_post_json

    def verify(self, token: str) -> Caller:
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError:
            raise AuthError(503, "auth_unavailable",
                            "Researchly could not check your sign-in just now. "
                            "Try again in a minute.") from None
        except (jwt.PyJWKClientError, jwt.DecodeError, jwt.InvalidTokenError):
            raise AuthError(401, "unauthorized", UNAUTHORIZED) from None
        # Pin the algorithm to the one the key itself declares, so a token's
        # own `alg` header can never choose how it is checked.
        if key.algorithm_name not in ALGORITHMS:
            raise AuthError(401, "unauthorized", UNAUTHORIZED)
        try:
            claims = jwt.decode(
                token, key.key, algorithms=[key.algorithm_name], audience=AUDIENCE,
                issuer=self.issuer, leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]})
        except jwt.InvalidTokenError:
            raise AuthError(401, "unauthorized", UNAUTHORIZED) from None
        sub = claims.get("sub")
        if claims.get("role") != "authenticated" or not isinstance(sub, str) \
                or not UUID.match(sub):
            raise AuthError(401, "unauthorized", UNAUTHORIZED)
        return Caller(user_id=sub, token=token)

    def load_settings(self, caller: Caller) -> dict:
        """The caller's stored settings, via RLS with their own token."""
        headers = {"apikey": self.publishable_key,
                   "Authorization": f"Bearer {caller.token}",
                   "Content-Type": "application/json",
                   "Accept": "application/json"}
        try:
            data = self._fetch(f"{self.url}/rest/v1/rpc/my_config", headers,
                               b"{}", HTTP_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            raise SettingsUnavailable(f"http_{e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise SettingsUnavailable("unreachable") from None
        except ValueError:                         # not JSON
            raise SettingsUnavailable("bad_response") from None
        if not isinstance(data, dict):
            raise SettingsUnavailable("bad_response")
        return data
