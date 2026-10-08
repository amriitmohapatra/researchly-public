"""The analysis, shaped for the wire (API contract v1).

The hosted service (services/engine) and the local Word server
(apps/word-addin/server.py) both answer the same contract. They used to
shape the response separately, and the local one fell behind the moment
the hosted one learned profiles and the brief (Codex review R1). Every
object beyond the suggestions is shaped here, once; the service validates
the result against its pydantic models, the local server sends it as is,
and a service test posts every contract option to the local server and
validates the answer.
"""

from __future__ import annotations

from typing import Optional


def profile_info(a) -> dict:
    p = a.profile
    return {"id": p.id, "label": p.label, "guessed": a.profile_guessed,
            "note": p.note, "rules_off": sorted(p.rules_off),
            "evidence": getattr(a, "profile_evidence", "") or ""}


def review_report(r: Optional[dict]) -> Optional[dict]:
    if r is None:
        return None
    return {
        "source": r["source"],
        "sections": list(r["sections"]),
        "words": int(r["metrics"]["words"]),
        "questions": [{"id": q["id"], "question": q["question"],
                       "status": q.get("status", "detected"),
                       "verdict": q["verdict"], "points": list(q["points"]),
                       "evidence": list(q["evidence"])}
                      for q in r["questions"]],
        "top_rules": [dict(t) for t in r["top_rules"]],
        "disclaimer": r.get("disclaimer", ""),
    }


def narrative_map(n: Optional[dict]) -> Optional[dict]:
    if n is None:
        return None
    return {
        "sections": [{
            "section": s["section"], "label": s["label"],
            "sentences": s["sentences"], "words": s["words"],
            "present": s["present"], "expected": s["expected"],
            "moves": [{k: m.get(k) for k in (
                "id", "label", "status", "question", "plain", "frame",
                "source", "evidence", "note", "learn_ref")}
                for m in s["moves"]],
        } for s in n["sections"]],
        "unmapped": list(n["unmapped"]),
        "missing_links": [{k: link.get(k) for k in (
            "section", "label", "code", "message", "source", "learn_ref")}
            | {"evidence": list(link.get("evidence") or [])}
            for link in n["missing_links"]],
        "hedging": [dict(h) for h in n["hedging"]],
        "note": n["note"],
        "profile": n.get("profile"),
        "source": n["source"],
    }


def checklist_report(c: Optional[dict]) -> Optional[dict]:
    if c is None:
        return None
    return {k: c[k] for k in ("id", "label", "design", "source", "suggested",
                              "reported", "total", "note")} | {
        "items": [{k: i[k] for k in ("id", "topic", "question", "plain",
                                     "sections", "status", "evidence")}
                  for i in c["items"]]}


def extras(a) -> dict:
    """Everything an analysis response carries beyond the suggestions."""
    return {
        "profile": profile_info(a),
        "review": review_report(a.review),
        "narrative": narrative_map(a.narrative),
        "checklist": checklist_report(a.checklist),
        "suggested_checklist": a.suggested_checklist,
    }
