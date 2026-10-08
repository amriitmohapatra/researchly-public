"""Engine calls are serialised per process; startup warms the engine."""

from __future__ import annotations

import logging
import threading
import time

from researchly import api

from researchly_service import engine_adapter
from researchly_service.schemas import AnalyzeOptions


def test_engine_calls_are_serialised(monkeypatch):
    active = {"now": 0, "max": 0}
    guard = threading.Lock()

    def slow_analyze(source, **kw):
        with guard:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.05)
        with guard:
            active["now"] -= 1
        return api.Analysis()

    monkeypatch.setattr(engine_adapter.api, "analyze", slow_analyze)
    threads = [threading.Thread(target=engine_adapter.run_analysis,
                                args=("text", "plain", AnalyzeOptions()))
               for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert active["max"] == 1


def test_concurrent_http_requests_all_succeed(client):
    results = []

    def go(i):
        r = client.post("/v1/analyze", json={
            "content": f"Results\n\nThe effect was large in district {i}."})
        results.append(r.status_code)
    threads = [threading.Thread(target=go, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 5


def test_startup_warms_the_engine(make_client, caplog):
    caplog.set_level(logging.INFO)
    make_client(warmup=True)
    assert api._NLP is not None                     # spaCy loaded
    warm = [r for r in caplog.records if getattr(r, "event", "") == "warmup"]
    assert warm, "no warm-up log line"
    assert warm[-1].rules_loaded > 0
    assert warm[-1].tiers["parser"] == "ready"
    assert "error_type" not in warm[-1].__dict__


def test_warm_up_never_raises(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("no")
    monkeypatch.setattr(engine_adapter.api, "analyze", boom)
    info = engine_adapter.warm_up()
    assert info["error_type"] == "RuntimeError"
