"""FastAPI application: routes of API contract v1 (ARCHITECTURE.md §7).

Route signatures and response models here are part of the contract and are
exported to packages/contract/openapi.json by `export_openapi.py`.

Layers, outermost first:

    CORSMiddleware            browser origins (RESEARCHLY_ALLOWED_ORIGINS)
    RequestContextMiddleware  request id · rate limit · 413 before parsing ·
                              500 error net · one JSON access-log line
    FastAPI                   422/400/404/405 → ErrorResponse (errors.py)
    routes                    → engine_adapter → researchly.api.analyze()

Run it with `python -m researchly_service` (see README.md).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import urllib.parse

from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import _core  # noqa: F401  (import path + tenant isolation first)
from . import __version__, accounts, engine_adapter, errors, logging_setup
from . import settings as settings_mod
from .errors import ApiError
from .middleware import RateLimiter, RequestContextMiddleware
from researchly import ingest, rules_grammar  # noqa: E402  (after _core)
from .schemas import (AnalyzeFileResponse, AnalyzeOptions, AnalyzeRequest,
                      AnalyzeWordRequest, AnalyzeWordResponse,
                      AnalyzeResponse, ErrorResponse, HealthResponse,
                      LearnCard, LearnResponse,
                      RulesResponse, Segment, SourceFormat, SourceInfo,
                      StructureItem)

ERRORS = {
    400: {"model": ErrorResponse, "description": "Malformed request"},
    401: {"model": ErrorResponse, "description": "Sign-in invalid or expired "
          "(unauthorized), or this needs an account (sign_in_required)"},
    413: {"model": ErrorResponse, "description": "Document too large"},
    422: {"model": ErrorResponse, "description": "Request failed validation"},
    429: {"model": ErrorResponse, "description": "Rate limited"},
    500: {"model": ErrorResponse, "description": "Engine error (no document text in the body)"},
    503: {"model": ErrorResponse, "description": "Sign-in could not be checked (auth_unavailable)"},
}
FILE_ERRORS = {**ERRORS,
               415: {"model": ErrorResponse,
                     "description": "Not a supported file type (unsupported_file)"}}

AUTH_HEADER_DOC = ("`Bearer <Supabase access token>` when signed in. Omit for "
                   "anonymous use.")

log = logging_setup.get("researchly.service")

router = APIRouter()


def _settings(request: Request) -> settings_mod.Settings:
    return request.app.state.settings


def _account(request: Request, authorization: Optional[str]) -> dict:
    """Resolve the caller: kwargs for engine_adapter.run_analysis.

    With accounts off (no Supabase configured) a token is ignored and the
    engine behaves as in S1. Raises ApiError for a bad token.
    """
    accts: Optional[accounts.Accounts] = request.app.state.accounts
    if accts is None:
        return {"signed_in": False}
    try:
        token = accounts.bearer_token(authorization)
        if token is None:
            return {"signed_in": False}
        caller = accts.verify(token)
    except accounts.AuthError as e:
        raise ApiError(e.status, e.code, e.message) from None
    request.state.signed_in = True
    try:
        return {"signed_in": True, "account": accts.load_settings(caller)}
    except accounts.SettingsUnavailable as e:
        return {"signed_in": True, "account_error": e.kind}


def _count_words(text: str) -> int:
    return len(text.split())


def _record(request: Request, resp: AnalyzeResponse) -> None:
    """Sizes and counts only: these feed the access-log line."""
    st = request.state
    st.suggestions = len(resp.suggestions)
    st.counts = dict(resp.counts)
    st.hidden_preferences = resp.hidden_preferences


@router.post("/v1/analyze", response_model=AnalyzeResponse, responses=ERRORS,
             operation_id="analyze", tags=["analysis"])
def analyze(req: AnalyzeRequest, request: Request,
            authorization: Optional[str] = Header(None, description=AUTH_HEADER_DOC)
            ) -> AnalyzeResponse:
    """Check one document and return typed, explained suggestions."""
    st = request.state
    st.content_chars = len(req.content)
    st.format = req.format.value
    s = _settings(request)
    who = _account(request, authorization)
    if (s.accounts_enabled and not who["signed_in"] and s.anon_max_words
            and _count_words(req.content) > s.anon_max_words):
        raise ApiError(401, "sign_in_required",
                       f"Without an account Researchly checks up to "
                       f"{s.anon_max_words:,} words at a time. Sign in to check "
                       "a whole chapter.")
    resp = engine_adapter.run_analysis(
        req.content, req.format.value, req.options,
        grammar_enabled=s.grammar_enabled, **who)
    _record(request, resp)
    return resp


@router.post("/v1/analyze-word", response_model=AnalyzeWordResponse,
             responses=ERRORS, operation_id="analyzeWord", tags=["analysis"])
def analyze_word(req: AnalyzeWordRequest, request: Request,
                 authorization: Optional[str] = Header(None, description=AUTH_HEADER_DOC)
                 ) -> AnalyzeWordResponse:
    """Check a Word document sent as its paragraphs (the Word add-in, S3).
    Each suggestion says which paragraph it is in and how to find it there,
    because Word has no character offsets."""
    paragraphs = [p.model_dump() for p in req.paragraphs]
    st = request.state
    st.content_chars = sum(len(p["text"]) for p in paragraphs)
    st.format = "word"
    s = _settings(request)
    who = _account(request, authorization)
    if (s.accounts_enabled and not who["signed_in"] and s.anon_max_words
            and sum(_count_words(p["text"]) for p in paragraphs)
            > s.anon_max_words):
        raise ApiError(401, "sign_in_required",
                       f"Without an account Researchly checks up to "
                       f"{s.anon_max_words:,} words at a time. Sign in to check "
                       "a whole chapter.")
    resp = engine_adapter.run_analysis(
        paragraphs, "word", req.options, grammar_enabled=s.grammar_enabled,
        response_cls=AnalyzeWordResponse, word_paragraphs=paragraphs, **who)
    _record(request, resp)
    return resp


def _filename(raw: str) -> str:
    """X-Researchly-Filename is percent-encoded UTF-8 (encodeURIComponent),
    because a header can't carry "Kapitel_ü.docx" as-is."""
    bad = ApiError(422, "invalid_request",
                   "x-researchly-filename must be the file's name, "
                   "percent-encoded.")
    try:
        name = urllib.parse.unquote(raw, errors="strict") if raw else ""
    except UnicodeDecodeError:
        raise bad from None
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or any(ord(c) < 32 or ord(c) == 127
                                           for c in name):
        raise bad
    return name


def _options(raw: Optional[str]) -> AnalyzeOptions:
    if not raw:
        return AnalyzeOptions()
    try:
        return AnalyzeOptions.model_validate_json(raw)
    except ValidationError as e:
        raise ApiError(422, "invalid_request",
                       "x-researchly-options: "
                       + errors.sanitized_validation_message(
                           [dict(err, loc=("options",) + tuple(err.get("loc") or ()))
                            for err in e.errors()]))


PUBLIC_STRUCTURE = frozenset({"figure", "table", "equation", "caption",
                              "citation"})
INGEST_STATUS = {"unsupported_file": 415, "unreadable_file": 422,
                 "payload_too_large": 413}

FILE_BODY = {"requestBody": {"required": True, "description": "The file's bytes.",
                             "content": {"application/octet-stream": {
                                 "schema": {"type": "string", "format": "binary"}}}}}


@router.post("/v1/analyze-file", response_model=AnalyzeFileResponse,
             responses=FILE_ERRORS, operation_id="analyzeFile",
             tags=["analysis"], openapi_extra=FILE_BODY)
async def analyze_file(
        request: Request,
        x_researchly_filename: str = Header(
            ..., max_length=1024,
            description="The file's name, percent-encoded (encodeURIComponent). "
                        "Only its extension is used; it is never logged."),
        x_researchly_options: Optional[str] = Header(
            None, max_length=16384, description="Optional JSON AnalyzeOptions."),
        authorization: Optional[str] = Header(None, description=AUTH_HEADER_DOC),
) -> AnalyzeFileResponse:
    """Check an uploaded file: .docx, .tex, an Overleaf .zip, .md/.qmd/.Rmd
    or .txt. The body is the raw file; it is read in memory and discarded."""
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "application/octet-stream":
        raise ApiError(415, "unsupported_media_type",
                       "Send the file as application/octet-stream.")
    name = _filename(x_researchly_filename)
    options = _options(x_researchly_options)
    s = _settings(request)
    who = await run_in_threadpool(_account, request, authorization)
    if s.accounts_enabled and not who["signed_in"]:
        raise ApiError(401, "sign_in_required",
                       "Sign in to check files. Without an account you can "
                       "paste up to "
                       f"{s.anon_max_words:,} words." if s.anon_max_words else
                       "Sign in to check files.")
    data = await request.body()
    request.state.upload_bytes = len(data)
    if not data:
        raise ApiError(422, "invalid_request", "The file is empty.")
    return await run_in_threadpool(_analyze_file, request, name, data, options,
                                   s.grammar_enabled, who)


def _analyze_file(request: Request, name: str, data: bytes,
                  options: AnalyzeOptions, grammar_enabled: bool,
                  who: dict) -> AnalyzeFileResponse:
    try:
        doc = ingest.load_bytes(name, data)
    except ingest.IngestError as e:
        raise ApiError(INGEST_STATUS.get(e.code, 422), e.code, e.message) from None
    del data
    fmt = {"markdown": "markdown", "latex": "latex"}.get(doc.kind, "plain")
    source_format = SourceFormat.docx if ingest.suffix_of(name) == ".docx" \
        else SourceFormat(fmt)
    st = request.state
    st.content_chars = len(doc.original)
    st.format = source_format.value
    info = SourceInfo(
        filename=name, format=source_format, text=doc.original,
        segments=[Segment(path=g.path, start=g.start, end=g.end,
                          source_start=g.source_start) for g in doc.segments],
        # Cross-references and labels are the engine's own bookkeeping
        # for the structural checks; the contract lists what a reader sees.
        structure=[StructureItem(kind=i.kind, start=i.start, end=i.end,
                                 label=i.label) for i in doc.structure
                   if i.kind in PUBLIC_STRUCTURE],
        warnings=list(doc.warnings))
    resp = engine_adapter.run_analysis(
        doc, doc.kind, options, grammar_enabled=grammar_enabled,
        response_cls=AnalyzeFileResponse, document=info, **who)
    _record(request, resp)
    return resp


@router.get("/v1/health", response_model=HealthResponse, operation_id="health",
            tags=["meta"])
def health(request: Request) -> HealthResponse:
    """Per-tier status. A degraded tier is reported, never hidden."""
    tiers = engine_adapter.health_tiers(_settings(request).grammar_enabled)
    return HealthResponse(
        status="degraded" if engine_adapter.is_degraded(tiers) else "ok",
        tiers=tiers, engine=engine_adapter.engine_info())


@router.get("/v1/rules", response_model=RulesResponse, operation_id="listRules",
            tags=["meta"])
def rules() -> RulesResponse:
    """The rule registry with why/source — powers Explain and settings UIs."""
    return RulesResponse(rules=engine_adapter.rule_infos(),
                         profiles=engine_adapter.profile_choices(),
                         checklists=engine_adapter.checklist_choices())


@router.get("/v1/learn", response_model=LearnResponse, operation_id="listLearn",
            tags=["meta"])
def learn_index() -> LearnResponse:
    """Every Learn card, grouped in reading order (S4). No document text."""
    return LearnResponse(cards=engine_adapter.learn_cards())


@router.get("/v1/learn/{card_id}", response_model=LearnCard,
            responses={404: {"model": ErrorResponse,
                             "description": "No such card"}},
            operation_id="getLearnCard", tags=["meta"])
def learn_card(card_id: str) -> LearnCard:
    """One Learn card, by the `learn_ref` a suggestion carries."""
    for card in engine_adapter.learn_cards():
        if card.id == card_id:
            return card
    raise ApiError(404, "not_found", "No Learn card has that id.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_setup.setup()
    _core.isolate()
    s: settings_mod.Settings = app.state.settings
    log.info("starting", extra={
        "event": "startup", "service_version": __version__,
        "core_version": engine_adapter.researchly.__version__,
        "allowed_origins": s.allowed_origins,
        "rate_limit_per_min": s.rate_limit_per_min,
        "lt_url_set": bool(rules_grammar.remote_url()),
        "accounts": s.accounts_enabled,
        "anon_max_words": s.anon_max_words,
        "grammar": s.grammar_enabled})
    if s.warmup:
        # Before the port opens, so Cloud Run's startup probe — and the
        # first user — only ever see a warm engine.
        info = engine_adapter.warm_up(s.grammar_enabled)
        log.info("warm", extra=dict(info, event="warmup"))
    yield


def create_app(settings: Optional[settings_mod.Settings] = None) -> FastAPI:
    s = settings or settings_mod.load()
    app = FastAPI(
        title="Researchly Engine API",
        version=__version__,
        summary="Explainable, section-aware feedback on research writing. "
                "Advises; never drafts.",
        description="Document text is processed in memory for the duration of "
                    "a request and is never stored, logged or used for training "
                    "(ARCHITECTURE.md ADR-02).",
        lifespan=lifespan,
    )
    app.state.settings = s
    app.state.limiter = RateLimiter(s.rate_limit_per_min)
    app.state.accounts = (accounts.Accounts(s.supabase_url,
                                            s.supabase_publishable_key)
                          if s.accounts_enabled else None)
    app.include_router(router)
    app.add_exception_handler(RequestValidationError,
                              errors.on_validation_error)
    app.add_exception_handler(StarletteHTTPException, errors.on_http_error)
    app.add_exception_handler(ApiError, errors.on_api_error)
    # add_middleware wraps: the LAST one added is the outermost. CORS goes
    # outside the request middleware so 413/429/500 replies still carry CORS
    # headers and the browser can read the error body.
    app.add_middleware(RequestContextMiddleware, settings=s,
                       limiter=app.state.limiter)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins,
        allow_methods=["GET", "POST"],
        # Authorization carries a bearer token, not a cookie, so
        # allow_credentials stays False.
        allow_headers=["Content-Type", "Authorization",
                       "X-Researchly-Filename", "X-Researchly-Options"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )
    return app


app = create_app()
