"""Flag precision from the owner's labels (S4 exit check).

Input: the JSON file the website's Label page exports (apps/web, /label).
It holds, per flag, only the rule id, its category and section, the
paragraph number and the verdict: never the text.

    {"version": 1, "labels": [
        {"paragraph": 1, "rule_id": "G106", "category": "improvement",
         "section": "discussion", "verdict": "useful"}, ...]}

Verdicts: "useful" (right, or worth acting on), "wrong" (a false flag),
"unsure" (left out of precision, counted separately).

Output: a Markdown report with precision overall, by category and by rule,
each with a Wilson 95% interval, because 50 paragraphs give small counts
and a bare percentage would overstate what they show.

    python3.10 ml/eval/label_precision.py labels.json [--min-flags 3]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

VERDICTS = ("useful", "wrong", "unsure")


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for k successes in n trials."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load(path) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        raise ValueError("not a Researchly labels file: no 'labels' list")
    out = []
    for i, x in enumerate(labels):
        if not isinstance(x, dict) or x.get("verdict") not in VERDICTS \
                or not isinstance(x.get("rule_id"), str):
            raise ValueError(f"label {i} is malformed")
        if set(x) - {"paragraph", "rule_id", "category", "section",
                     "verdict"}:
            raise ValueError(f"label {i} carries unexpected fields; labels "
                             "hold no text")
        out.append(x)
    return out


def tally(labels: list, key) -> dict:
    t: dict = defaultdict(lambda: {"useful": 0, "wrong": 0, "unsure": 0})
    for x in labels:
        t[key(x)][x["verdict"]] += 1
    return t


def _row(name: str, c: dict) -> str:
    n = c["useful"] + c["wrong"]
    if n == 0:
        return f"| {name} | {c['useful']} | {c['wrong']} | {c['unsure']} | – | – |"
    lo, hi = wilson(c["useful"], n)
    return (f"| {name} | {c['useful']} | {c['wrong']} | {c['unsure']} | "
            f"{c['useful'] / n:.0%} | {lo:.0%} to {hi:.0%} |")


def report(labels: list, min_flags: int = 3) -> str:
    paragraphs = len({x.get("paragraph") for x in labels})
    total = tally(labels, lambda x: "All flags")["All flags"]
    head = ("| | Useful | Wrong | Unsure | Precision | 95% interval |\n"
            "|---|---|---|---|---|---|")
    L = ["# Flag precision from labelled paragraphs", "",
         f"{len(labels)} flags in {paragraphs} paragraphs. Precision is "
         "useful / (useful + wrong); unsure flags are left out. The interval "
         "is Wilson's 95% interval.", "", head, _row("All flags", total), "",
         "## By category", "", head]
    for k, c in sorted(tally(labels, lambda x: x.get("category", "?")).items()):
        L.append(_row(k, c))
    L += ["", f"## By rule (rules with at least {min_flags} labelled flags)",
          "", head]
    for k, c in sorted(tally(labels, lambda x: x["rule_id"]).items()):
        if sum(c.values()) >= min_flags:
            L.append(_row(k, c))
    worst = sorted(((c["wrong"], k) for k, c in
                    tally(labels, lambda x: x["rule_id"]).items()
                    if c["wrong"]), reverse=True)[:5]
    if worst:
        L += ["", "Most false flags: " + ", ".join(f"{k} ({n})"
                                                     for n, k in worst) + "."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels")
    ap.add_argument("--min-flags", type=int, default=3)
    a = ap.parse_args(argv)
    try:
        print(report(load(a.labels), a.min_flags))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
