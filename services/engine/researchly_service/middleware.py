"""The request middleware: id, size cap, rate limit, error net, access log.

A pure ASGI middleware (not `BaseHTTPMiddleware`), so it sees the raw
request before FastAPI reads the body and can catch every exception the app
raises. In order, for each HTTP request it:

1. assigns a `request_id` (uuid4 hex; never taken from the client) and
   returns it as `X-Request-ID` on every response;
2. rate-limits by client IP (sliding 60 s window, in memory, per instance);
3. rejects a body larger than the cap **before reading it** when
   Content-Length says so, and caps chunked bodies while buffering;
4. runs the app, and turns ANY exception into a 500 `ErrorResponse` without
   re-raising — Starlette's ServerErrorMiddleware would otherwise log the
   exception with its message, which may quote the document;
5. writes one JSON access-log line with fixed, text-free fields.
"""

from __future__ import annotations

import collections
import time
import uuid
from typing import Deque, Dict, Optional

from . import logging_setup
from .errors import INTERNAL_MESSAGE, error_bytes

log = logging_setup.get("researchly.service")
access = logging_setup.get("researchly.access")

# Paths that may appear in logs verbatim. Anything else is logged as
# "other": a raw path is client-chosen and could carry text.
KNOWN_ROUTES = {"/v1/analyze", "/v1/analyze-file", "/v1/health", "/v1/rules", "/docs",
                "/openapi.json", "/redoc"}
UNLIMITED_PATHS = {"/v1/health"}
UPLOAD_PATHS = {"/v1/analyze-file"}
BODY_METHODS = {"POST", "PUT", "PATCH"}


class RateLimiter:
    """Sliding-window counter per key. Single-threaded use (event loop)."""

    def __init__(self, per_minute: int, window_s: float = 60.0,
                 max_keys: int = 10_000):
        self.per_minute = per_minute
        self.window_s = window_s
        self.max_keys = max_keys
        self._hits: Dict[str, Deque[float]] = {}

    def check(self, key: str, now: Optional[float] = None) -> Optional[int]:
        """None if allowed (and counted); else seconds until a slot frees."""
        if self.per_minute <= 0:
            return None
        now = time.monotonic() if now is None else now
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self.max_keys:
                self._prune(now)
            q = self._hits[key] = collections.deque()
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.per_minute:
            return max(1, int(self.window_s - (now - q[0])) + 1)
        q.append(now)
        return None

    def _prune(self, now: float) -> None:
        stale = [k for k, q in self._hits.items()
                 if not q or now - q[-1] >= self.window_s]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:     # still full: drop oldest
            for k in list(self._hits)[: len(self._hits) // 2]:
                del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


def client_ip(scope, trusted_hops: int) -> str:
    """The caller's IP. With N trusted proxies in front (Cloud Run's front
    end appends exactly one X-Forwarded-For entry), the real client is the
    N-th entry from the right; anything left of it is client-supplied and
    could be forged to dodge the rate limit."""
    if trusted_hops > 0:
        for name, value in scope.get("headers") or []:
            if name == b"x-forwarded-for":
                parts = [p.strip() for p in value.decode("latin-1").split(",")
                         if p.strip()]
                if len(parts) >= trusted_hops:
                    return parts[-trusted_hops]
                break
    client = scope.get("client")
    return client[0] if client else "unknown"


def _header(scope, name: bytes) -> Optional[bytes]:
    for k, v in scope.get("headers") or []:
        if k == name:
            return v
    return None


class RequestContextMiddleware:
    def __init__(self, app, settings, limiter: RateLimiter):
        self.app = app
        self.settings = settings
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        t0 = time.perf_counter()
        rid = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = rid
        path = scope.get("path", "")
        route = path if path in KNOWN_ROUTES else "other"
        method = scope.get("method", "")
        status_box = {"status": 0, "started": False}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
                status_box["started"] = True
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode()))
                message = dict(message, headers=headers)
            await send(message)

        async def reply_error(status, code, message, extra_headers=()):
            state["error_code"] = code
            body = error_bytes(code, message, rid)
            headers = [(b"content-type", b"application/json"),
                       (b"content-length", str(len(body)).encode())]
            headers.extend(extra_headers)
            await send_with_id({"type": "http.response.start",
                                "status": status, "headers": headers})
            await send_with_id({"type": "http.response.body", "body": body})

        failure = None
        try:
            try:
                # 1. rate limit
                if method != "OPTIONS" and path not in UNLIMITED_PATHS:
                    wait = self.limiter.check(
                        client_ip(scope, self.settings.trusted_proxy_hops))
                    if wait is not None:
                        return await reply_error(
                            429, "rate_limited",
                            "Too many requests from this address; try again "
                            f"in {wait} s.",
                            [(b"retry-after", str(wait).encode())])

                # 2. body size, decided before the body is read
                if method in BODY_METHODS:
                    cap = (self.settings.max_upload_bytes
                           if path in UPLOAD_PATHS
                           else self.settings.max_body_bytes)
                    too_big = too_large_message(cap)
                    raw_len = _header(scope, b"content-length")
                    if raw_len is not None:
                        try:
                            declared = int(raw_len)
                        except ValueError:
                            return await reply_error(
                                400, "malformed_request",
                                "Content-Length is not a number.")
                        if declared > cap:
                            return await reply_error(413, "payload_too_large",
                                                     too_big)
                    else:
                        # Chunked: buffer up to the cap, then replay.
                        body, ok = await _read_capped(receive, cap)
                        if not ok:
                            return await reply_error(413, "payload_too_large",
                                                     too_big)
                        receive = _replay(body, receive)

                await self.app(scope, receive, send_with_id)
            except Exception as exc:                   # the error net
                # Type and code location only — never the message or locals.
                failure = {"error_type": type(exc).__name__,
                           "frames": logging_setup.safe_frames(
                               exc.__traceback__)}
                # Drop the exception (its message and its frames' locals
                # hold text) and log/reply OUTSIDE this block: anything that
                # prints "the exception being handled" — a failing log
                # handler, a debug hook — then has nothing to print.
                del exc
            if failure is not None:
                state["error_code"] = "internal"
                log.error("unhandled exception", extra=dict(
                    failure, event="unhandled_exception", request_id=rid,
                    route=route))
                if not status_box["started"]:
                    await reply_error(500, "internal", INTERNAL_MESSAGE)
                # Deliberately not re-raised (see module docstring).
        finally:
            fields = {
                "event": "request", "request_id": rid, "method": method,
                "route": route, "status": status_box["status"],
                "latency_ms": int(round((time.perf_counter() - t0) * 1000)),
            }
            # Never the filename, the token or the user id.
            for key in ("content_chars", "format", "suggestions", "counts",
                        "hidden_preferences", "upload_bytes", "signed_in"):
                if key in state:
                    fields[key] = state[key]
            if "error_code" in state:
                fields["code"] = state["error_code"]
            access.info("request", extra=fields)


def too_large_message(cap: int) -> str:
    mb = cap / (1024 * 1024)
    return (f"The request is larger than {mb:.0f} MB. Split the document "
            "and check it in parts.")


async def _read_capped(receive, cap: int):
    chunks, size = [], 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > cap:
            return b"", False
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks), True


def _replay(body: bytes, original):
    """Hand the buffered body to the app once, then defer to the real
    channel (so a disconnect is still reported when it actually happens)."""
    sent = {"done": False}

    async def receive():
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await original()
    return receive
