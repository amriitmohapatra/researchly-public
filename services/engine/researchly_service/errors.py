"""One error shape for every non-2xx response: `ErrorResponse` (contract v1).

Two layers produce errors, and both build their bodies here:

- **FastAPI exception handlers** (registered in main.py) for request
  validation (422 / malformed JSON 400) and routing errors (404/405);
- **the request middleware** (middleware.py) for what must be decided before
  or around the app: oversized bodies (413, rejected unread), rate limiting
  (429) and any unhandled exception (500).

Privacy: pydantic's validation errors carry the offending `input` — for
`content` that is the user's document — and some messages quote it. So the
422 message is rebuilt from the error *type* and the field *location* only,
locations are limited to the contract's own field names (an unknown key a
client sends is itself client data), and `input`/`ctx` are never copied
except for schema-derived numbers and enum choices.
"""

from __future__ import annotations

import json
from typing import Iterable

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import ErrorBody, ErrorResponse

# Field names of the request contract. Only these may be echoed in a message.
KNOWN_FIELDS = {"body", "format", "content", "options", "show_preferences",
                "disabled_rules", "query", "path", "header",
                "x-researchly-filename", "x-researchly-options"}

_FRIENDLY = {
    "missing": "is required",
    "string_too_short": "must not be empty",
    "string_type": "must be a string",
    "bool_type": "must be true or false",
    "bool_parsing": "must be true or false",
    "list_type": "must be a list",
    "dict_type": "must be a JSON object",
    "model_type": "must be a JSON object",
    "model_attributes_type": "must be a JSON object",
    "extra_forbidden": "is not a field of this request",
}

STATUS_CODES = {
    400: "malformed_request",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal",
}

STATUS_MESSAGES = {
    400: "The request could not be read.",
    404: "No such endpoint.",
    405: "This endpoint does not accept that method.",
    415: "Send the request body as application/json (files: "
         "application/octet-stream to /v1/analyze-file).",
}

INTERNAL_MESSAGE = ("The engine failed while checking this document. Nothing "
                    "was stored. Quote the request id if you report it.")


def error_payload(code: str, message: str, request_id: str) -> dict:
    return ErrorResponse(error=ErrorBody(
        code=code, message=message, request_id=request_id)).model_dump()


def error_bytes(code: str, message: str, request_id: str) -> bytes:
    return json.dumps(error_payload(code, message, request_id),
                      ensure_ascii=False).encode("utf-8")


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _respond(request: Request, status: int, code: str, message: str
             ) -> JSONResponse:
    request.state.error_code = code
    return JSONResponse(status_code=status,
                        content=error_payload(code, message,
                                              request_id_of(request)))


def _loc(parts: Iterable) -> str:
    out = []
    for p in parts:
        if isinstance(p, int):
            out.append(f"[{p}]")
        elif isinstance(p, str) and p in KNOWN_FIELDS:
            out.append(("." if out else "") + p)
        else:
            out.append(("." if out else "") + "<unknown field>")
    return "".join(out) or "request"


def _describe(err: dict) -> str:
    """One validation error as text built from type + location only."""
    etype = str(err.get("type", "invalid"))
    ctx = err.get("ctx") or {}
    if etype == "string_too_long":
        what = f"is too long (at most {int(ctx.get('max_length', 0))} " \
               f"characters)"
    elif etype == "too_long":
        what = f"has too many items (at most {int(ctx.get('max_length', 0))})"
    elif etype == "enum":
        # `expected` is rendered from the schema's enum, not from input.
        what = f"must be one of {ctx.get('expected', 'the allowed values')}"
    else:
        what = _FRIENDLY.get(etype, f"is invalid ({etype})")
    return f"{_loc(err.get('loc') or ())} {what}"


def sanitized_validation_message(errors: list) -> str:
    parts = [_describe(e) for e in errors[:5]]
    more = len(errors) - len(parts)
    if more > 0:
        parts.append(f"and {more} more")
    return "; ".join(parts) + "."


async def on_validation_error(request: Request,
                              exc: RequestValidationError) -> JSONResponse:
    errors = list(exc.errors())
    if any(e.get("type") == "json_invalid" for e in errors):
        return _respond(request, 400, "malformed_json",
                        "The request body is not valid JSON.")
    return _respond(request, 422, "invalid_request",
                    sanitized_validation_message(errors))


class ApiError(Exception):
    """Raised by a route to answer with an ErrorResponse. `message` must be
    user-safe: fixed copy, never request content."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


async def on_api_error(request: Request, exc: ApiError) -> JSONResponse:
    resp = _respond(request, exc.status, exc.code, exc.message)
    if exc.status == 401:
        resp.headers["WWW-Authenticate"] = 'Bearer realm="researchly"'
    return resp


async def on_http_error(request: Request,
                        exc: StarletteHTTPException) -> JSONResponse:
    status = exc.status_code
    code = STATUS_CODES.get(status, "http_error")
    # Fixed messages: never exc.detail, which a future handler might fill
    # from the request.
    message = STATUS_MESSAGES.get(status, "The request could not be served.")
    resp = _respond(request, status, code, message)
    if exc.headers:
        for k, v in exc.headers.items():
            resp.headers[k] = v
    return resp
