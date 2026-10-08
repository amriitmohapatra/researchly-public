"""The precision report from labels (S4 exit check). Synthetic labels."""

import json

import pytest

import label_precision as lp


def labels(*rows):
    return [{"paragraph": p, "rule_id": r, "category": c,
             "section": "discussion", "verdict": v} for p, r, c, v in rows]


def test_wilson_interval_brackets_the_rate():
    lo, hi = lp.wilson(8, 10)
    assert lo < 0.8 < hi and 0 <= lo and hi <= 1
    assert lp.wilson(0, 0) == (0.0, 0.0)


def test_report_counts_and_leaves_unsure_out():
    ls = labels((1, "G106", "improvement", "useful"),
                (1, "G106", "improvement", "wrong"),
                (2, "S001", "correction", "useful"),
                (2, "S001", "correction", "useful"),
                (3, "S001", "correction", "unsure"))
    out = lp.report(ls, min_flags=2)
    assert "5 flags in 3 paragraphs" in out
    assert "| All flags | 3 | 1 | 1 | 75% |" in out
    assert "| S001 | 2 | 0 | 1 | 100% |" in out
    assert "Most false flags: G106 (1)." in out


def test_a_labels_file_with_text_is_refused(tmp_path):
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"labels": [{"rule_id": "G106", "verdict":
                                         "useful", "text": "a sentence"}]}))
    with pytest.raises(ValueError):
        lp.load(p)


def test_the_web_pages_export_is_read():
    """ml/eval/fixtures/web-labels.json is what the website's Label page
    exports for a known session (apps/web/tests/unit/labels.test.ts checks
    the page produces exactly this file), so the two cannot drift apart."""
    from pathlib import Path
    ls = lp.load(Path(__file__).parent / "fixtures" / "web-labels.json")
    out = lp.report(ls, min_flags=2)
    assert "4 flags in 2 paragraphs" in out
    assert "| All flags | 2 | 1 | 1 | 67% |" in out
    assert "| C201 | 1 | 0 | 1 | 100% |" in out


def test_cli_round_trip(tmp_path, capsys):
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"version": 1, "labels": labels(
        (1, "C303", "convention", "useful"))}))
    assert lp.main([str(p)]) == 0
    assert "| All flags | 1 | 0 | 0 | 100% |" in capsys.readouterr().out
