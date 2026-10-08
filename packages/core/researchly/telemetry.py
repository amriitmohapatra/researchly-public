"""Local usage telemetry: the data that makes tuning honest.

Every event stays on this machine, in ~/.researchly/telemetry.jsonl —
nothing is transmitted anywhere. The point (research/04, dogfooding report):
dismissal rates per rule are the ground truth for which rules earn their
keep on YOUR writing, and should drive future attenuation.

Events: shown · goto · applied · dismissed · muted
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

DIR = Path.home() / ".researchly"
FILE = DIR / "telemetry.jsonl"

VALID_EVENTS = {"shown", "goto", "applied", "dismissed", "muted"}


def log_event(event: str, rule_id: str, *, section: str = "unknown",
              source: str = "word", count: int = 1) -> bool:
    """Append one event. Returns False (silently) on any problem —
    telemetry must never break the tool."""
    try:
        if event not in VALID_EVENTS or not rule_id:
            return False
        DIR.mkdir(exist_ok=True)
        rec = {"t": int(time.time()), "event": event, "rule": rule_id,
               "section": section, "source": source, "n": int(count)}
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return True
    except Exception:
        return False


def read_events() -> list[dict]:
    if not FILE.exists():
        return []
    out = []
    with open(FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def summarize(events: list[dict] | None = None) -> dict:
    """Per-rule tallies + a keep-rate verdict.

    keep_rate = (shown - dismissed - muted) / shown  … how often a shown
    suggestion survived. Low keep-rate rules are attenuation candidates —
    exactly the 'track dismissals per rule and auto-attenuate' principle.
    """
    events = read_events() if events is None else events
    per_rule: dict[str, dict] = defaultdict(
        lambda: {"shown": 0, "goto": 0, "applied": 0,
                 "dismissed": 0, "muted": 0})
    for e in events:
        rule = e.get("rule")
        ev = e.get("event")
        if rule and ev in VALID_EVENTS:
            per_rule[rule][ev] += int(e.get("n", 1))

    report = {}
    for rule, c in per_rule.items():
        shown = max(c["shown"], 1)
        engaged = c["applied"] + c["goto"]
        rejected = c["dismissed"] + c["muted"]
        keep = max(0.0, (c["shown"] - rejected) / shown)
        if c["shown"] < 10:
            verdict = "not enough data"
        elif keep < 0.4:
            verdict = "attenuation candidate — mostly rejected"
        elif engaged >= 0.25 * c["shown"]:
            verdict = "earning its keep — actively used"
        else:
            verdict = "tolerated — kept but rarely acted on"
        report[rule] = {**c, "keep_rate": round(keep, 2),
                        "verdict": verdict}
    return dict(sorted(report.items(),
                       key=lambda kv: kv[1]["shown"], reverse=True))
