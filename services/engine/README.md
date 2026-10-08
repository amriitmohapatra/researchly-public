# Researchly engine service

The hosted HTTP face of `packages/core` (ARCHITECTURE.md §5.2, §7). FastAPI,
stateless, one `researchly.api.analyze()` call per request. Document text
lives only in the memory of the request that carries it.

## Endpoints (contract v1)

The contract is `researchly_service/schemas.py`, exported to
`packages/contract/openapi.json`. Do not change shapes without regenerating
it (`python -m researchly_service.export_openapi`, then `--check` in CI).

| Method | Path | Returns |
|---|---|---|
| `POST` | `/v1/analyze` | `AnalyzeResponse`: suggestions (with `why`, `source`, stable `id`), counts, hidden-preference count, metrics, sections, per-tier health, engine info, `elapsed_ms` |
| `GET` | `/v1/health` | `HealthResponse`: `ok`, or `degraded` when a tier the service runs is down (the opt-in `gec` tier never degrades it) |
| `GET` | `/v1/rules` | `RulesResponse`: the rule registry with why/source |

Every non-2xx response is an `ErrorResponse` (`{"error": {code, message,
request_id}}`) and every response carries `X-Request-ID`:

| Status | `code` | When |
|---|---|---|
| 400 | `malformed_json`, `malformed_request` | body is not JSON; bad Content-Length |
| 404 / 405 | `not_found`, `method_not_allowed` | unknown path or method |
| 413 | `payload_too_large` | body over `RESEARCHLY_MAX_BODY_BYTES`, refused **before it is read** |
| 422 | `invalid_request` | fails the schema (message built from field + error type only) |
| 429 | `rate_limited` | over the per-IP limit; `Retry-After` header |
| 500 | `internal` | anything else; logged by exception type only |

## Run locally

From the repo root, with the core's dependencies installed:

```bash
cd services/engine
pip install -r requirements-dev.txt
RESEARCHLY_ENV=development python -m researchly_service     # :8080
curl localhost:8080/v1/health
curl localhost:8080/v1/analyze -H 'content-type: application/json' \
     -d '{"content": "Methods\n\nThe model was calibrated by the authors."}'
```

`researchly` is found automatically in a repo checkout
(`researchly_service/_core.py` adds `packages/core` to `sys.path`). Without
`RESEARCHLY_LT_URL` the grammar tier starts LanguageTool locally, which needs
Java 17+.

With Docker (engine + LanguageTool sidecar, as on Cloud Run):

```bash
cd services/engine && docker compose up --build
```

Build the image on its own (context = repo root, filtered by `/.dockerignore`):

```bash
docker build -f services/engine/Dockerfile -t researchly-engine .
```

Tests and the contract check:

```bash
cd services/engine
python -m pytest tests/ -q -p no:cacheprovider
python -m researchly_service.export_openapi --check      # "contract up to date"
```

Latency (ARCHITECTURE.md Q1/Q2), synthetic text only:

```bash
python bench.py --url http://localhost:8080      # or --in-process
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | listen port (Cloud Run sets it) |
| `RESEARCHLY_MODE` | `service` | health wording for the hosted engine (never "nothing leaves this machine") |
| `RESEARCHLY_ENV` | `production` | `development` allows `http://localhost:3000` by default |
| `RESEARCHLY_ALLOWED_ORIGINS` | none (prod) | comma-separated CORS origins; `*` is refused |
| `RESEARCHLY_LT_URL` | unset | LanguageTool server, e.g. `http://localhost:8010`; unset = local JVM |
| `RESEARCHLY_GRAMMAR` | `on` | `off` = this deployment runs no grammar (health says `disabled`, not degraded) |
| `RESEARCHLY_MAX_BODY_BYTES` | `8388608` | request body cap (8 MiB; must admit 1M four-byte characters) |
| `RESEARCHLY_RATE_LIMIT_PER_MIN` | `30` | per client IP, per instance; `0` disables |
| `RESEARCHLY_TRUSTED_PROXY_HOPS` | `0` | X-Forwarded-For entries added by trusted proxies (Cloud Run: `1`) |
| `RESEARCHLY_WARMUP` | `on` | warm spaCy, rules and LanguageTool before opening the port |

CORS allows only `GET`/`POST`, only the `Content-Type` request header, no
credentials, and exposes `X-Request-ID` and `Retry-After`.

## Privacy (non-negotiable #2, ADR-02)

- **No text in logs.** One JSON line per request with fixed fields
  (`request_id`, route template, status, latency, `content_chars`, format,
  suggestion counts). Never the body, the query string, the raw path, a
  suggestion's `text`, or an exception message. Exceptions are logged as
  class name + `file:line in function` frames; Python warnings as their
  category. uvicorn's access log is off (it prints the raw request line).
- **No text in errors.** 422 messages are rebuilt from field location and
  error type; pydantic's `input` is never copied, and unknown field names
  (client data) are shown as `<unknown field>`. 500 bodies are a fixed
  message.
- **No text in health.** A failed grammar check is recorded by exception
  type only, because `/v1/health` is public and shared by every caller.
- **No per-user files.** The service builds a default `Config()` per request
  and applies the request's options; it never calls `config.load()`, and
  `_core.isolate()` points `~/.researchly/config.toml`,
  `~/.researchly/dictionary.txt` and the GEC model folder at a path that
  cannot exist. `tests/test_isolation.py` plants all three and proves they
  have no effect.
- **The Q6 canary suite** (`tests/test_privacy_canary.py`, release-blocking)
  sends a canary string through a success, validation errors, malformed
  JSON, oversized bodies, forced internal errors and a failing grammar
  backend, and asserts it appears in no log record, no JSON log line, no
  stdout/stderr output and no error body.
- **The image holds no third-party text.** `/.dockerignore` is an allow-list
  (core package + service only); the build context is ~300 KB.

## Concurrency

spaCy's pipeline and the LanguageTool client are process-wide singletons,
not documented as thread-safe, and FastAPI runs sync routes in a threadpool.
So analyses are serialised by one lock per process, and Cloud Run's
`containerConcurrency` is **1** to match (`deploy/cloudrun.service.yaml`):
extra requests go to another instance or wait in Cloud Run's queue, where
autoscaling can see them, instead of behind the lock. `/v1/health` and
`/v1/rules` do not take the lock.

The rate limit is in memory, per instance: with `maxScale: 2` a client can
get up to 2× the configured rate. Accounts (S2) replace it with per-user
limits.

## Measured (dev machine, 2026-10-03)

4-core x86_64 sandbox, engine container + LanguageTool 6.8 container on the
same host. **Not a Cloud Run instance**; staging numbers tick Q1/Q2.

| Workload | p50 | p95 | Target |
|---|---|---|---|
| Q1 paragraph, 311 words, via HTTP | 243 ms | 309 ms | p95 ≤ 800 ms |
| Q2 chapter, 10,228 words, via HTTP | 4.35 s | 4.68 s | p95 ≤ 6 s |
| Q1 paragraph, in-process | 217 ms | 246 ms | |
| Q2 chapter, in-process | 4.13 s | 4.30 s | |

The chapter is ~2.0 s spaCy parse + ~2.0 s LanguageTool, run one after the
other. Cold start (container start → warm, port open): ~5 s. At the
contract's 1M-character cap: 74 s end to end, engine peak ~2.8 GiB,
LanguageTool ~1.3 GiB.

## Deploy

`deploy/cloudrun.service.yaml` (Cloud Run, `asia-southeast1`, engine +
LanguageTool sidecar). Placeholders `${ENGINE_IMAGE}`, `${ALLOWED_ORIGINS}`
and `${PROJECT_ID}` are filled by the deploy workflow.
