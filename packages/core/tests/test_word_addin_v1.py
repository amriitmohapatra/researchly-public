"""The Word add-in's local server speaks contract v1 (S3, ADR-02 local mode).

The hosted taskpane's "This computer" engine is apps/word-addin/server.py.
These tests prove it answers /v1/analyze-word and /v1/health with the SAME
shapes as the hosted engine (validated with the engine service's own
pydantic models when they are installed), and that its CORS lets only the
hosted taskpane's origin in, with the private-network preflight a public
HTTPS page needs to reach localhost. All text is synthetic.
"""

import http.client
import importlib.util
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "word-addin"))

import server as addin_server  # noqa: E402

HOSTED = "https://researchly-chi.vercel.app"

PARAS = [
    {"text": "Methods", "style": "Heading1", "kind": "body"},
    {"text": "In order to fit the model, we performed an estimation of the "
             "transmission rate. The the priors were weak.",
     "style": "Normal", "kind": "body"},
    {"text": "Discussion", "style": "Heading 1", "kind": "body"},
    {"text": "This proves that the intervention works.", "style": "Normal",
     "kind": "body"},
    {"text": "Methods", "style": "Normal", "kind": "table"},
]


def _schemas():
    """The hosted engine's contract models, loaded by path (no service
    start-up), or skip when pydantic is not installed."""
    pytest.importorskip("pydantic")
    path = ROOT / "services" / "engine" / "researchly_service" / "schemas.py"
    spec = importlib.util.spec_from_file_location("_contract_schemas", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def result():
    return addin_server.analyze_word(
        {"paragraphs": PARAS,
         "options": {"show_preferences": False, "disabled_rules": [],
                     "mode": "revise"}})


def test_analyze_word_matches_the_contract(result):
    schemas = _schemas()
    parsed = schemas.AnalyzeWordResponse.model_validate(result)
    assert parsed.schema_version == "1"
    assert parsed.mode.value == "revise"
    assert parsed.coverage.paragraphs == len(PARAS)
    assert parsed.coverage.table_paragraphs == 1
    assert "footnotes" in parsed.coverage.not_checked


def test_locations_find_the_flagged_words_in_their_paragraph(result):
    assert result["suggestions"], "the synthetic draft should draw suggestions"
    for s in result["suggestions"]:
        loc = s["location"]
        text = PARAS[loc["paragraph"]]["text"]
        span = text[loc["start"]:loc["end"]]
        if loc["exact"]:
            assert span == loc["snippet"]
            # `occurrence` copies of the snippet come before this one
            assert text[:loc["start"]].count(loc["snippet"]) == loc["occurrence"]
        else:
            assert span.startswith(loc["snippet"])
    rules = {s["rule_id"] for s in result["suggestions"]}
    assert "G102" in rules              # "performed an estimation of"


def test_same_ids_as_the_hosted_engine(result):
    s = result["suggestions"][0]
    assert s["id"] == addin_server._fingerprint(
        s["rule_id"], s["span"]["start"], s["span"]["end"], s["text"])


def test_request_mutes_and_mode_apply(result):
    some = result["suggestions"][0]["rule_id"]
    muted = addin_server.analyze_word(
        {"paragraphs": PARAS, "options": {"disabled_rules": [some]}})
    assert some not in {s["rule_id"] for s in muted["suggestions"]}
    draft = addin_server.analyze_word(
        {"paragraphs": PARAS, "options": {"mode": "draft"}})
    assert draft["mode"] == "draft"
    assert draft["hidden_by_mode"] >= 0


@pytest.mark.parametrize("payload", [
    {},
    {"paragraphs": []},
    {"paragraphs": [{"text": 3}]},
    {"paragraphs": [{"text": "x", "kind": "footnote"}]},
    {"paragraphs": [{"text": "x", "colour": "red"}]},
    {"paragraphs": [{"text": "x"}], "options": {"mode": "final"}},
    {"paragraphs": [{"text": "x"}], "options": {"disabled_rules": "G101"}},
    {"paragraphs": [{"text": "x"}], "extra": 1},
])
def test_bad_requests_are_refused(payload):
    with pytest.raises(addin_server.ContractError) as e:
        addin_server.parse_word_request(payload)
    assert e.value.status == 422


def test_health_matches_the_contract():
    schemas = _schemas()
    h = schemas.HealthResponse.model_validate(addin_server.health_v1())
    assert {t.tier for t in h.tiers} >= {"parser", "spelling"}


# ---------------------------------------------------------------------------
# Over HTTP: CORS, preflight, private network, error shapes
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def port():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), addin_server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    data = json.dumps(body).encode() if body is not None else None
    c.request(method, path, body=data, headers=headers or {})
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, raw


def test_preflight_allows_the_hosted_taskpane_with_private_network(port):
    status, h, _ = _req(port, "OPTIONS", "/v1/analyze-word", headers={
        "Origin": HOSTED,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
        "Access-Control-Request-Private-Network": "true"})
    assert status == 204
    assert h["access-control-allow-origin"] == HOSTED
    assert h["access-control-allow-private-network"] == "true"
    assert "POST" in h["access-control-allow-methods"]
    assert "content-type" in h["access-control-allow-headers"].lower()


def test_preflight_refuses_other_origins(port):
    status, h, _ = _req(port, "OPTIONS", "/v1/analyze-word", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Private-Network": "true"})
    assert status == 403
    assert "access-control-allow-origin" not in h
    assert "access-control-allow-private-network" not in h


def test_post_over_http_with_cors(port):
    status, h, raw = _req(port, "POST", "/v1/analyze-word",
                          {"paragraphs": PARAS[:2]},
                          {"Origin": HOSTED, "Content-Type": "application/json"})
    assert status == 200, raw[:200]
    assert h["access-control-allow-origin"] == HOSTED
    body = json.loads(raw)
    assert body["schema_version"] == "1" and "coverage" in body


def test_post_from_another_origin_is_refused(port):
    status, h, raw = _req(port, "POST", "/v1/analyze-word",
                          {"paragraphs": PARAS[:2]},
                          {"Origin": "https://evil.example",
                           "Content-Type": "application/json"})
    assert status == 403
    assert "access-control-allow-origin" not in h
    assert json.loads(raw)["error"]["code"] == "origin_not_allowed"


def test_errors_use_the_contract_shape_and_never_quote_text(port):
    secret = "Unpublished finding: R0 was 9.7 in the cohort."
    status, h, raw = _req(port, "POST", "/v1/analyze-word",
                          {"paragraphs": [{"text": secret, "kind": "nope"}]},
                          {"Origin": HOSTED, "Content-Type": "application/json"})
    assert status == 422
    err = json.loads(raw)["error"]
    assert set(err) == {"code", "message", "request_id"}
    assert secret not in raw.decode()
    assert h["access-control-allow-origin"] == HOSTED


def test_health_over_http(port):
    status, h, raw = _req(port, "GET", "/v1/health", headers={"Origin": HOSTED})
    assert status == 200
    assert h["access-control-allow-origin"] == HOSTED
    assert json.loads(raw)["status"] in ("ok", "degraded")


def test_old_local_taskpane_routes_still_work(port):
    status, _, raw = _req(port, "GET", "/ping")
    assert status == 200 and json.loads(raw)["ok"] is True
    status, _, _ = _req(port, "GET", "/taskpane.html")
    assert status == 200
