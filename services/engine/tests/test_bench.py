"""bench.py: the latency harness that ticks Q1/Q2 must not crash on its own options."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "bench", Path(__file__).resolve().parents[1] / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def fake_runner():
    calls = []

    def run(text):
        calls.append(text)
        return 10.0, 5, 3, True
    return run, calls


def test_zero_runs_skips_the_size_without_running_it():
    # Regression: --n-chapter 0 used to raise "cannot convert float NaN to integer".
    run, calls = fake_runner()
    assert bench.measure(run, "text", 0, warmup=3) == {"n": 0}
    assert calls == []          # no warm-up either


def test_measure_reports_percentiles():
    run, calls = fake_runner()
    r = bench.measure(run, "text", 4, warmup=1)
    assert len(calls) == 5
    assert r["n"] == 4 and r["p50_ms"] == 10 and r["server_p50_ms"] == 5
    assert r["grammar_ok"] is True


def test_negative_counts_are_rejected():
    with pytest.raises(SystemExit):
        bench.main(["--url", "http://x", "--n-chapter", "-1"])


def test_main_prints_skipped_size(monkeypatch, capsys):
    run, _ = fake_runner()
    monkeypatch.setattr(bench, "http_runner", lambda url: run)
    assert bench.main(["--url", "http://x", "--n-chapter", "0",
                       "--n-paragraph", "2", "--warmup", "0"]) == 0
    out = capsys.readouterr().out
    assert "chapter   skipped (n=0)" in out
    assert "Q1 paragraph" in out
