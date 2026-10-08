"""/v1/health: degraded only for tiers the service runs; truthful wording;
a remote LanguageTool sidecar is probed, and an unreachable one is reported
with a reason and a remedy."""

from __future__ import annotations

import pytest

from researchly import health as core_health
from researchly import rules_grammar
from researchly.health import TierStatus

from researchly_service import engine_adapter
from researchly_service.schemas import TierHealth

_GLOBALS = ("_TOOL", "_FAILED", "_STATE", "_DETAIL", "_LOCALE", "_URL",
            "_FAILED_AT")


def _t(tier, ok, state):
    return TierHealth(tier=tier, label=tier, ok=ok, state=state)


def test_degraded_rules():
    base = [_t("parser", True, "ready"), _t("spelling", True, "ready"),
            _t("grammar", True, "ready")]
    assert not engine_adapter.is_degraded(base + [_t("gec", False,
                                                     "missing")])
    assert not engine_adapter.is_degraded(base + [_t("gec", False,
                                                     "disabled")])
    assert engine_adapter.is_degraded(base + [_t("gec", False, "error")])
    assert engine_adapter.is_degraded(
        [_t("parser", True, "ready"), _t("grammar", False, "error")])
    assert engine_adapter.is_degraded(
        [_t("parser", True, "ready"), _t("grammar", False, "missing")])
    # The operator configured the deployment without grammar.
    assert not engine_adapter.is_degraded(
        [_t("parser", True, "ready"), _t("grammar", False, "disabled")])
    # "unstarted" but ok (installed, will start) is not degraded.
    assert not engine_adapter.is_degraded([_t("grammar", True, "unstarted")])


def _fake_status(grammar_ok, grammar_state):
    def fake(cfg=None, nlp=None, probe=False):
        return [TierStatus("parser", "Sentence parser", True, "ready", "x"),
                TierStatus("spelling", "Spelling", True, "ready", "x"),
                TierStatus("grammar", "Grammar", grammar_ok, grammar_state,
                           "why", "remedy"),
                TierStatus("gec", "Learned corrections", False, "missing",
                           "no local model", "")]
    return fake


def test_status_ok_when_only_the_opt_in_gec_tier_is_off(client, monkeypatch):
    monkeypatch.setattr(core_health, "engine_status",
                        _fake_status(True, "ready"))
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"
    assert any(t["tier"] == "gec" and not t["ok"] for t in body["tiers"])


def test_status_degraded_when_grammar_is_down(client, monkeypatch):
    monkeypatch.setattr(core_health, "engine_status",
                        _fake_status(False, "error"))
    body = client.get("/v1/health").json()
    assert body["status"] == "degraded"
    g = next(t for t in body["tiers"] if t["tier"] == "grammar")
    assert g["detail"] and g["remedy"]


def test_grammar_off_by_operator_is_not_degraded(make_client):
    c = make_client(grammar_enabled=False, warmup=False)
    body = c.get("/v1/health").json()
    g = next(t for t in body["tiers"] if t["tier"] == "grammar")
    assert g["state"] == "disabled"
    assert body["status"] == ("ok" if all(
        t["ok"] for t in body["tiers"] if t["tier"] in ("parser", "spelling"))
        else "degraded")
    # and the analysis honours it
    r = c.post("/v1/analyze", json={"content": "This are wrong."})
    assert not any(s["rule_id"] == "LT001" for s in r.json()["suggestions"])


def test_live_health_reflects_reality(client):
    """No mocks: status is degraded iff a configured tier is not ok."""
    body = client.get("/v1/health").json()
    tiers = [TierHealth(**t) for t in body["tiers"]]
    assert body["status"] == ("degraded" if engine_adapter.is_degraded(tiers)
                              else "ok")
    parser = next(t for t in tiers if t.tier == "parser")
    assert parser.ok and parser.state == "ready"     # warmed at startup


def test_hosted_wording_never_claims_local_only(client):
    for path in ("/v1/health",):
        body = client.get(path).json()
        for t in body["tiers"]:
            assert "this machine" not in t["detail"], t
    body = client.post("/v1/analyze", json={"content": "Some text."}).json()
    for t in body["health"]:
        assert "this machine" not in t["detail"], t
    sp = next(t for t in body["health"] if t["tier"] == "spelling")
    assert "your dictionary" not in sp["detail"]


@pytest.fixture
def remote_state(monkeypatch):
    saved = {k: getattr(rules_grammar, k) for k in _GLOBALS}
    for k, v in (("_TOOL", None), ("_FAILED", False), ("_STATE", "unstarted"),
                 ("_DETAIL", ""), ("_LOCALE", None), ("_URL", None),
                 ("_FAILED_AT", 0.0)):
        setattr(rules_grammar, k, v)
    core_health.reset_probe_cache()
    yield
    for k, v in saved.items():
        setattr(rules_grammar, k, v)
    core_health.reset_probe_cache()


def test_unreachable_sidecar_is_reported(make_client, monkeypatch,
                                         remote_state):
    monkeypatch.setenv(rules_grammar.REMOTE_ENV, "http://127.0.0.1:9")
    c = make_client()                          # warm-up tries and fails
    body = c.get("/v1/health").json()
    assert body["status"] == "degraded"
    g = next(t for t in body["tiers"] if t["tier"] == "grammar")
    assert not g["ok"] and g["state"] == "error"
    assert "not responding" in g["detail"]
    assert "sidecar" in g["remedy"]
    # analysis still works, and says grammar is down
    r = c.post("/v1/analyze", json={"content": "This are wrong."})
    assert r.status_code == 200
    g2 = next(t for t in r.json()["health"] if t["tier"] == "grammar")
    assert not g2["ok"]
