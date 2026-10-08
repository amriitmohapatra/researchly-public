"""Researchly local server for the Word add-in.

Serves the taskpane web app and a /check endpoint, all on localhost.
Everything runs on your machine — no document text ever leaves it.

S3: it is also the hosted add-in's "This computer" engine (ADR-02 local
mode). `POST /v1/analyze-word` and `GET /v1/health` answer with the same
contract shapes as the hosted engine (packages/contract), so the taskpane
at https://researchly-chi.vercel.app/word can check against this machine
instead of the cloud. Only that page's origin (and the dev server's) may
call them from a browser (CORS, with the private-network preflight a
public HTTPS page needs to reach localhost).

Usage:
    python server.py            # http://localhost:3517
    python server.py --port N
    python server.py --https    # requires cert.pem/key.pem (see README)

Python stdlib only (plus the researchly package + spaCy already installed
for the CLI). Start this, then open the Researchly add-in in Word.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "packages" / "core"))  # make `researchly` importable

from researchly import api                             # noqa: E402
from researchly import config as config_mod            # noqa: E402
from researchly import telemetry                       # noqa: E402
from researchly import transform                       # noqa: E402
from researchly import wordloc                         # noqa: E402
from researchly import packs as packs_mod              # noqa: E402
from researchly import shapes                          # noqa: E402
from researchly.profiles import DOCUMENT_TYPES         # noqa: E402

_NLP_LOCK = threading.Lock()


def get_nlp():
    """Shared with every other surface; api sets max_length identically."""
    with _NLP_LOCK:
        return api.get_nlp()


def run_check(payload: dict) -> dict:
    paragraphs = payload.get("paragraphs") or []

    analysis = api.analyze(
        paragraphs,
        nlp=get_nlp(),
        disabled=(set(payload["disabled"])
                  if payload.get("disabled") is not None else None),
        show_preferences=payload.get("show_preferences"),
    )
    doc = analysis.document

    out = []
    for s in analysis.suggestions:
        para, start_in = doc.locate(s.start)
        para_text = paragraphs[para].get("text") or ""
        end_in = min(s.end - doc.para_offsets[para], len(para_text))
        d = s.to_dict()
        d.update(_locator(para_text, start_in, end_in))
        d["para"] = para
        d["start_in_para"] = start_in
        d["end_in_para"] = end_in
        d["why"] = " ".join(s.why.split())
        out.append(d)

    result = analysis.to_dict()
    result["suggestions"] = out
    result["coverage"] = _coverage(paragraphs, doc)
    return result


def _coverage(paragraphs: list, doc) -> dict:
    """What was and was not read, stated plainly.

    Office JS `body.paragraphs` excludes footnotes, endnotes, headers,
    footers, text boxes and comments. Researchly never checked them and
    never said so, which reads as "nothing to flag" rather than "not looked
    at" — the same silence-is-ambiguous failure as the dead grammar tier.
    """
    return {
        "paragraphs": len(paragraphs),
        "table_paragraphs": len(getattr(doc, "table_spans", [])),
        "not_checked": ["footnotes", "endnotes", "headers and footers",
                        "text boxes", "comments"],
    }


def _locator(para_text: str, start_in: int, end_in: int) -> dict:
    """How the client should find this span again in Word.

    Word has no offset-addressable API, so the taskpane re-finds the text by
    searching. Two things make that safe: the snippet must be the FULL span
    (a truncated one can match somewhere else), and the occurrence index must
    be counted with the same string the client will search for.
    """
    span = para_text[start_in:end_in]
    # `search` chokes on its own wildcard characters and on very long
    # needles; when we cannot hand over an exact literal, say so rather than
    # let the client guess with a prefix.
    exact = bool(span) and len(span) <= 255 and "^" not in span
    snippet = span if exact else span[:180].replace("^", "")
    occurrence = para_text[:start_in].count(snippet) if snippet else 0
    return {"snippet": snippet, "occurrence": occurrence, "exact": exact,
            "expected": span}


# ---------------------------------------------------------------------------
# Contract v1 for the hosted taskpane's "This computer" mode (S3)
# ---------------------------------------------------------------------------

# Browser origins allowed to call /v1/* here. Everything else gets no CORS
# headers, so a page on any other site cannot read the answers.
ALLOWED_ORIGINS = frozenset({
    "https://researchly-chi.vercel.app",   # the hosted taskpane (/word)
    "http://localhost:3000",               # apps/web's dev server
    "http://localhost:3517",               # this server's own pages
    "https://localhost:3517",              # ... with --https
})

SCHEMA_VERSION = "1"
MAX_WORD_PARAGRAPHS = 50_000       # packages/contract MAX_WORD_PARAGRAPHS
MAX_PARAGRAPH_CHARS = 1_000_000
MAX_CONTENT_CHARS = 1_000_000      # the hosted engine's cap on the whole text
MAX_STYLE_CHARS = 200
MAX_DISABLED_RULES = 200
MAX_BODY_BYTES = 64 * 1024 * 1024
MODES = ("draft", "revise")
# Every option of the contract's AnalyzeOptions (packages/contract).
OPTION_KEYS = {"show_preferences", "disabled_rules", "mode",
               "document_type", "review", "narrative", "checklist"}
CHECKLISTS = {"auto"} | set(packs_mod.checklists())
# Tiers whose being off never makes this engine "degraded" (as the hosted one).
_OPTIONAL_STATES = {"gec": {"missing", "disabled"}}


class ContractError(Exception):
    """A request the contract refuses: becomes an ErrorResponse."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict:
    """ErrorResponse: never contains document text."""
    return {"error": {"code": code, "message": message,
                      "request_id": uuid.uuid4().hex[:16]}}


def _fingerprint(rule_id: str, start: int, end: int, text: str) -> str:
    """Same id as the hosted engine (engine_adapter.fingerprint)."""
    raw = "\x1f".join((rule_id, str(start), str(end), text))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _engine_info() -> dict:
    import researchly
    return {"service_version": "word-addin-local",
            "core_version": researchly.__version__,
            "rules_loaded": api.ensure_rules_loaded()}


def parse_word_request(payload) -> tuple:
    """Validate an AnalyzeWordRequest by hand (stdlib only, like the rest
    of this server). Returns (paragraphs, show_preferences, disabled, mode,
    extra), where extra holds document_type, review, narrative and
    checklist. Every option of the contract is accepted: a service test
    posts them all here (Codex review R1)."""
    bad = lambda msg: ContractError(422, "invalid_request", msg)  # noqa: E731
    if not isinstance(payload, dict):
        raise bad("the body must be a JSON object")
    extra = set(payload) - {"paragraphs", "options"}
    if extra:
        raise bad(f"unknown field(s): {', '.join(sorted(extra))}")
    paras = payload.get("paragraphs")
    if not isinstance(paras, list) or not paras:
        raise bad("paragraphs must be a non-empty list")
    if len(paras) > MAX_WORD_PARAGRAPHS:
        raise ContractError(413, "payload_too_large",
                            f"at most {MAX_WORD_PARAGRAPHS:,} paragraphs at a time")
    clean = []
    total = 0
    for i, p in enumerate(paras):
        if not isinstance(p, dict) or set(p) - {"text", "style", "kind"}:
            raise bad(f"paragraph {i} must be {{text, style, kind}}")
        text = p.get("text", "")
        style = p.get("style", "")
        kind = p.get("kind", "body")
        if not isinstance(text, str) or len(text) > MAX_PARAGRAPH_CHARS:
            raise bad(f"paragraph {i}: text must be a string")
        if not isinstance(style, str) or len(style) > MAX_STYLE_CHARS:
            raise bad(f"paragraph {i}: style must be a string of at most "
                      f"{MAX_STYLE_CHARS} characters")
        if kind not in ("body", "table"):
            raise bad(f"paragraph {i}: kind must be body or table")
        total += len(text)
        clean.append({"text": text, "style": style, "kind": kind})
    if total > MAX_CONTENT_CHARS:
        raise ContractError(413, "payload_too_large",
                            f"at most {MAX_CONTENT_CHARS:,} characters at a time")

    opts = payload.get("options") or {}
    if not isinstance(opts, dict) or set(opts) - OPTION_KEYS:
        raise bad("options must be {" + ", ".join(sorted(OPTION_KEYS)) + "}")
    prefs = opts.get("show_preferences", False)
    if not isinstance(prefs, bool):
        raise bad("show_preferences must be true or false")
    disabled = opts.get("disabled_rules") or []
    if (not isinstance(disabled, list) or len(disabled) > MAX_DISABLED_RULES
            or not all(isinstance(r, str) for r in disabled)):
        raise bad("disabled_rules must be a list of rule ids")
    mode = opts.get("mode")
    if mode is not None and mode not in MODES:
        raise bad("mode must be draft or revise")
    extra = {}
    doc_type = opts.get("document_type")
    if doc_type is not None and doc_type not in DOCUMENT_TYPES:
        raise bad("document_type must be one of " + ", ".join(DOCUMENT_TYPES))
    extra["document_type"] = doc_type
    for flag in ("review", "narrative"):
        v = opts.get(flag, False)
        if not isinstance(v, bool):
            raise bad(f"{flag} must be true or false")
        extra[flag] = v
    checklist = opts.get("checklist")
    if checklist is not None and checklist not in CHECKLISTS:
        raise bad("checklist must be one of " + ", ".join(sorted(CHECKLISTS)))
    extra["checklist"] = checklist
    return clean, prefs, disabled, mode, extra


def _word_suggestion(s, doc, paragraphs: list) -> dict:
    """One suggestion in the contract's WordSuggestion shape (as
    services/engine/researchly_service/engine_adapter.to_suggestion)."""
    conf = float(s.confidence if s.confidence is not None else 1.0)
    return {
        "id": _fingerprint(s.rule_id, s.start, s.end, s.text),
        "rule_id": s.rule_id,
        "rule_name": s.rule_name,
        "category": s.category.value,
        "tier": s.tier,
        "span": {"start": max(0, s.start), "end": max(0, s.end),
                 "line": max(0, s.line), "col": max(0, s.col)},
        "text": s.text,
        "section": s.section or "unknown",
        "message": s.message,
        "why": s.why,
        "plain": s.plain,
        "source": s.source,
        "learn_ref": s.learn_ref,
        "replacement": s.replacement,
        "fix_safety": "safe" if s.fix_safety == "safe" else "review",
        "confidence": min(1.0, max(0.0, conf)),
        "location": wordloc.locate(doc, paragraphs, s.start, s.end),
    }


def analyze_word(payload) -> dict:
    """POST /v1/analyze-word: an AnalyzeWordResponse, computed here.

    Settings: this computer's shared config (~/.researchly/config.toml,
    which every local surface reads), plus the request's options, which can
    only ADD mutes (as on the hosted engine); the request's mode wins.
    """
    t0 = time.perf_counter()
    paragraphs, prefs, disabled, mode, extra = parse_word_request(payload)
    cfg = config_mod.load()
    cfg.show_preferences = bool(cfg.show_preferences or prefs)
    cfg.disabled = set(cfg.disabled) | set(disabled)
    if mode is not None:
        cfg.mode = mode
    if extra["document_type"] is not None:
        cfg.document_type = extra["document_type"]
    a = api.analyze(paragraphs, nlp=get_nlp(), cfg=cfg,
                    with_review=extra["review"],
                    with_narrative=extra["narrative"],
                    checklist=extra["checklist"])
    doc = a.document
    out = {
        "schema_version": SCHEMA_VERSION,
        "signed_in": False,
        "mode": a.config.mode,
        "hidden_by_mode": a.hidden_by_mode,
        "suggestions": [_word_suggestion(s, doc, paragraphs)
                        for s in a.suggestions],
        "counts": dict(a.counts),
        "hidden_preferences": a.hidden_preferences,
        "metrics": a.metrics.to_dict() if a.metrics else None,
        "sections_detected": list(a.sections_detected),
        "health": [t.to_dict() for t in a.health],
        "engine": _engine_info(),
        "elapsed_ms": 0,
        "warnings": list(doc.warnings) if doc is not None else [],
        "coverage": wordloc.coverage(paragraphs, doc),
        **shapes.extras(a),
    }
    out["elapsed_ms"] = int(round((time.perf_counter() - t0) * 1000))
    return out


def health_v1() -> dict:
    """GET /v1/health: HealthResponse (no probe: it must answer at once)."""
    tiers = [t.to_dict() for t in api.status(config_mod.load(), probe=False)]
    degraded = any(
        not t["ok"] and t["state"] != "disabled"
        and t["state"] not in _OPTIONAL_STATES.get(t["tier"], set())
        for t in tiers)
    return {"status": "degraded" if degraded else "ok", "tiers": tiers,
            "engine": _engine_info()}


def cors_headers(origin, private_network: bool = False) -> dict:
    """CORS for the hosted taskpane only. `private_network`: the preflight
    asked for Access-Control-Allow-Private-Network (Chrome's check before a
    public HTTPS page may call a server on localhost)."""
    if origin not in ALLOWED_ORIGINS:
        return {}
    h = {"Access-Control-Allow-Origin": origin,
         "Vary": "Origin",
         "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
         "Access-Control-Allow-Headers": "Content-Type, Accept",
         "Access-Control-Expose-Headers": "X-Request-ID",
         "Access-Control-Max-Age": "600"}
    if private_network:
        h["Access-Control-Allow-Private-Network"] = "true"
    return h


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "web"), **kwargs)

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _json(self, code: int, obj: dict, headers=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def _cors(self, preflight: bool = False) -> dict:
        pna = preflight and (self.headers.get(
            "Access-Control-Request-Private-Network", "").lower() == "true")
        return cors_headers(self.headers.get("Origin"), private_network=pna)

    def do_OPTIONS(self):
        # CORS preflight for the hosted taskpane's local mode (S3).
        if self._route() not in ("/v1/analyze-word", "/v1/health"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        headers = self._cors(preflight=True)
        self.send_response(204 if headers else 403)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _v1_post(self):
        """POST /v1/analyze-word. Text is held for this request only and
        never written anywhere (no telemetry on this path)."""
        cors = self._cors()
        origin = self.headers.get("Origin")
        if origin is not None and not cors:
            return self._json(403, error_body(
                "origin_not_allowed",
                "This page may not use Researchly on this computer."))
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            return self._json(413, error_body(
                "payload_too_large", "The document is too large to check at once."),
                cors)
        try:
            payload = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            return self._json(422, error_body(
                "invalid_request", "The body is not valid JSON."), cors)
        try:
            return self._json(200, analyze_word(payload), cors)
        except ContractError as e:
            return self._json(e.status, error_body(e.code, e.message), cors)
        except Exception as e:  # reported by type only: messages can quote text
            return self._json(500, error_body(
                "internal", f"The local engine failed ({type(e).__name__})."),
                cors)

    def do_GET(self):
        if self._route() == "/v1/health":
            return self._json(200, health_v1(), self._cors())
        if self.path == "/ping":
            # Rules register on import, which check() does lazily — so this
            # must trigger it or the taskpane reports "0 rules" until the
            # first check.
            return self._json(200, {"ok": True, "app": "researchly",
                                    "rules": api.ensure_rules_loaded()})
        if self.path.startswith("/status"):
            # Which tiers are actually running. The taskpane shows this so a
            # dead grammar engine can never again look like clean prose.
            cfg = config_mod.load()
            probe = "probe=1" in self.path
            statuses = api.status(cfg, probe=probe)
            from researchly.health import summary_line
            return self._json(200, {
                "health": [t.to_dict() for t in statuses],
                "summary": summary_line(statuses),
                "config": cfg.to_dict()})
        if self.path == "/rules":
            api.ensure_rules_loaded()          # registration is lazy
            from researchly.engine import REGISTRY
            return self._json(200, {"rules": [
                {"id": r.id, "name": r.name, "category": r.category.value,
                 "short": r.short, "why": " ".join(r.why.split()),
                 "source": r.source, "tier": r.tier,
                 "fix_safety": r.fix_safety}
                for r in REGISTRY.values()]})
        return super().do_GET()

    def do_POST(self):
        if self._route() == "/v1/analyze-word":
            return self._v1_post()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            return self._json(400, {"error": f"bad payload: {e}"})
        if self.path == "/check":
            try:
                return self._json(200, run_check(payload))
            except Exception as e:  # prototype: surface the error in the pane
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        if self.path == "/polish":
            try:
                text = payload.get("text") or ""
                if not text.strip():
                    return self._json(400, {"error": "empty selection"})
                # Muted rules come from the SHARED config; a payload
                # override remains possible but the taskpane no longer
                # sends one (parity with every other surface).
                disabled = (set(payload["disabled"])
                            if payload.get("disabled") is not None
                            else config_mod.load().disabled)
                result = transform.polish(text, get_nlp(),
                                          disabled=disabled)
                return self._json(200, result.to_dict())
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        if self.path == "/review":
            # The critical-reader report (Wallace & Wray + the Toulmin
            # argument scan) over the whole document. Built from the same
            # Word paragraphs as /check so style-based headings survive.
            try:
                paragraphs = payload.get("paragraphs") or []
                if not paragraphs:
                    return self._json(400, {"error": "empty document"})
                from researchly import review as review_mod
                doc = api.build_document(paragraphs)
                r = review_mod.build_review(doc, get_nlp())
                return self._json(200, {
                    "report": review_mod.render_review(r), "data": r})
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        if self.path == "/dictionary":
            # "Add to dictionary" from an S001 card: persist the word
            # locally (~/.researchly/dictionary.txt) so it is never
            # flagged again on any surface.
            from researchly import spelling as _spelling
            word = str(payload.get("word") or "").strip()
            if not word or not word.replace("-", "").isalpha():
                return self._json(400, {"error": "not a valid word"})
            ok = _spelling.add_to_user_dictionary(word)
            return self._json(200 if ok else 500,
                              {"ok": ok, "word": word.lower()})
        if self.path == "/config":
            # The settings panel. Writes ~/.researchly/config.toml, which the
            # CLI, macOS app, Windows app and LSP all read — so a rule muted
            # in Word is muted everywhere, instead of living in this
            # taskpane's localStorage where nothing else could see it.
            try:
                cfg = config_mod.load()
                if payload.get("mute"):
                    config_mod.mute_rule(str(payload["mute"]))
                elif payload.get("unmute"):
                    config_mod.unmute_rule(str(payload["unmute"]))
                else:
                    cfg = cfg.with_overrides(**{
                        k: payload[k] for k in
                        ("show_preferences", "locale", "document_type",
                         "aggressiveness", "grammar_tier", "gec_tier",
                         "disabled")
                        if k in payload})
                    if not config_mod.save_user(cfg):
                        return self._json(500, {"error": "could not save"})
                return self._json(200, {"ok": True,
                                        "config": config_mod.load().to_dict()})
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        if self.path == "/telemetry":
            # local-only usage log (~/.researchly/telemetry.jsonl) — this is
            # the data `researchly stats` reports on. Never fails the UI.
            for ev in payload.get("events") or []:
                telemetry.log_event(
                    str(ev.get("event", "")), str(ev.get("rule", "")),
                    section=str(ev.get("section", "unknown")),
                    source="word", count=int(ev.get("n", 1)))
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "unknown endpoint"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3517)
    ap.add_argument("--https", action="store_true",
                    help="serve over HTTPS using cert.pem/key.pem in this "
                         "folder (see README troubleshooting)")
    args = ap.parse_args()

    # Warm the model in the background so the first check is fast.
    threading.Thread(target=get_nlp, daemon=True).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    scheme = "http"
    if args.https:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(HERE / "cert.pem", HERE / "key.pem")
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    print(f"Researchly server: {scheme}://localhost:{args.port}/taskpane.html")
    print("Keep this running while you write in Word. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
