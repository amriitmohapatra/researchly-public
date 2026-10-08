"""The critical reader's brief (Wallace & Wray's five critical-synopsis
questions, met in the owner's training; see sources.py).

An on-demand, document-level pass that plays the friendly-sceptical
reader. Every line is answered from deterministic evidence the engine
already computed: no model, every statement traceable to a rule or a
read-out.

    A. Why am I reading this?          (yours to answer)
    B. What are the authors trying to achieve?   -> aim signals
    C. What are they claiming?         -> claim inventory (causal, consensus)
    D. How convincing are the claims?  -> warranting evidence: gap statement,
                                          calibration balance, overclaims,
                                          novelty risks, limitations section,
                                          argument links
    E. What use can be made of this?   -> significance signals

Surfaces get it from `api.analyze(..., with_review=True)` as
`Analysis.review` (S4: the website and the Word add-in). The CLI's
`researchly review` and the old local add-in call `build_review` directly.
The wording below is user-visible: plain words, no internal references
(test_explanations.py applies the same ban as to rule text).
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from .discourse import abstract_lens
from .discourse import argument as argument_mod
from . import metrics as metrics_mod
from . import profiles as profiles_mod
from . import sources
from .document import Document
from .engine import REGISTRY, check

SOURCE = sources.cite("WW+course-U1")

DISCLAIMER = ("This brief points to what a critical reader would ask, "
              "from signals in the wording. It does not establish whether "
              "the science is sound.")

QUESTIONS = (
    ("A", "Why am I reading this?"),
    ("B", "What are the authors trying to achieve?"),
    ("C", "What are they claiming?"),
    ("D", "How convincing are the claims?"),
    ("E", "What use can be made of this?"),
)


def build_review(text, nlp, kind: str = "plain", *, suggestions=None,
                 spacy_doc=None, metrics=None,
                 profile: Optional[profiles_mod.Profile] = None,
                 disabled=()) -> dict:
    """`text` may be a str or an already-built Document (the Word server
    passes a Document so style-based headings survive into the review).
    `api.analyze` passes its own suggestions, parse and metrics so the
    document is analysed once."""
    doc = text if isinstance(text, Document) else Document.from_text(text,
                                                                     kind)
    if profile is None:
        profile = profiles_mod.resolve(
            getattr(getattr(doc, "config", None), "document_type", None),
            doc)[0]
        doc.default_section = doc.default_section or profile.body_section
    if suggestions is None:
        suggestions = check(doc, nlp, disabled={"LT001"},
                            show_preferences=True, spacy_doc=spacy_doc)
    suggestions = [s for s in suggestions if s.rule_id != "LT001"]
    if metrics is None:
        metrics = metrics_mod.compute(spacy_doc or nlp(doc.masked), doc)
    mets = metrics
    by_rule = Counter(s.rule_id for s in suggestions)
    moves = abstract_lens.analyze(doc.masked)
    sections = sorted({h.section for h in doc.headings}) or ["(none)"]
    has_limitations = "limitations" in sections

    # The review reads the document's argument structure from the shared
    # argument objects, not only from rule hits.
    arg_objects = argument_mod.build_argument(doc, spacy_doc=spacy_doc)
    arg = argument_mod.summarize(arg_objects)
    # Checks muted by the writer or switched off by the article type were
    # not run: their silence is "not assessed", never "not found" (Codex
    # review R4).
    off = set(disabled) | set(profile.rules_off)
    claims_seen = any("claim" in r.all_roles
                      for o in arg_objects for r in o.supporting_spans)

    def sentence_of(s):
        text = doc.original
        a = max(text.rfind(". ", 0, s.start), text.rfind("\n", 0, s.start))
        b_dot = text.find(". ", s.end)
        b_nl = text.find("\n", s.end)
        ends = [x for x in (b_dot, b_nl) if x != -1]
        b = min(ends) + 1 if ends else len(text)
        return " ".join(text[a + 1:b].split())[:180]

    def hits(rule_id):
        return [s for s in suggestions if s.rule_id == rule_id]

    causal = hits("C303")
    r = {
        "source": SOURCE,
        "profile": profile.id,
        "argument": arg,
        "sections": sections,
        "expected_missing": [s for s in profile.expected
                             if s not in sections],
        "metrics": mets.to_dict(),
        "aim": moves["aim"],
        "significance": moves["significance"],
        "has_introduction": "introduction" in sections,
        "gap_present": (not hits("D902") and moves["gap"]["present"]
                        and "introduction" in sections),
        "gap_evidence": moves["gap"]["evidence"],
        "gap_expected": profile.gap_expected,
        "gap_assessed": "D902" not in off,
        "causal_assessed": "C303" not in off,
        "consensus_assessed": "E704" not in off,
        "claims_seen": claims_seen or bool(causal) or bool(hits("C302")),
        "causal_claims": [s.message for s in causal],
        "causal_evidence": [sentence_of(s) for s in causal[:5]],
        "not_assessed": sorted(r_id for r_id in off
                               if r_id in ("C301", "C302", "C303", "E704",
                                           "E705", "D902", "AB802")),
        "disclaimer": DISCLAIMER,
        "uncited_consensus": len(hits("E704")),
        "overclaims": len(hits("C302")),
        "novelty_risks": len(hits("E705")),
        "hedge_stacks": len(hits("C301")),
        "has_limitations": has_limitations,
        "limitations_expected": profile.limitations_expected,
        "abstract_missing": ([s.message for s in hits("AB802")] or None),
        "total_suggestions": len(suggestions),
        "by_rule": dict(by_rule.most_common(8)),
        "top_rules": [{"id": k, "short": _short(k), "count": v}
                      for k, v in by_rule.most_common(5)],
    }
    r["questions"] = brief(r)
    return r


def _short(rule_id: str) -> str:
    rule = REGISTRY.get(rule_id)
    return rule.short if rule is not None else rule_id


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def brief(r: dict) -> list:
    """The five questions, each with a status, a one-line verdict, the
    points behind it and the sentences it rests on. Plain words.

    status: "yours" (A), "detected", "not_detected" (the signals found
    nothing, which is not proof of absence), "not_assessed" (the check was
    off) or "not_applicable" (the part of the document is not there).
    Every positive assertion carries evidence (Codex review R4)."""
    m = r["metrics"]
    out = []
    structured = r["sections"] != ["(none)"]

    def add(key, status, verdict, points=(), evidence=()):
        question = dict(QUESTIONS)[key]
        out.append({"id": key, "question": question, "status": status,
                    "verdict": verdict,
                    "points": [p for p in points if p],
                    "evidence": [e for e in evidence if e]})

    # A
    add("A", "yours", "Yours to answer: what do you need from this document?",
        ["The brief below reads the text as a sceptical reader would, from "
         "signals in the wording alone."])

    # B
    if r["aim"]["present"]:
        add("B", "detected", "An aim is stated.",
            evidence=[r["aim"]["evidence"]])
    else:
        add("B", "not_detected", "No explicit aim was detected.",
            ["Where does the reader learn what question this document "
             "answers? One sentence near the end of the introduction "
             "usually does it. If you have one, it may be worded in a way "
             "the signals do not recognise."])

    # C
    if not r["causal_assessed"]:
        add("C", "not_assessed",
            "Not assessed: the check for causal claims is off for this "
            "check (muted, or switched off by the article type).",
            ["Turn it back on to see the causal claims listed here."])
    else:
        points, verdicts = [], []
        if r["causal_claims"]:
            verdicts.append(_count(len(r["causal_claims"]), "causal claim",
                                   "causal claims")
                            + " detected; check that the design supports "
                            + ("it" if len(r["causal_claims"]) == 1 else "each"))
            points += r["causal_claims"][:5]
        else:
            verdicts.append("no unhedged causal claims were detected")
        if r["uncited_consensus"]:
            verdicts.append(_count(r["uncited_consensus"],
                                   "'is known' claim without a citation",
                                   "'is known' claims without a citation"))
            points.append("A claim that something is known, accepted or "
                          "considered true needs a citation: who says?")
        elif not r["consensus_assessed"]:
            points.append("Claims that something 'is known' were not "
                          "checked: that check is off.")
        status = "detected" if (r["causal_claims"] or r["uncited_consensus"]) \
            else "not_detected"
        text = "; ".join(verdicts)
        add("C", status, text[:1].upper() + text[1:] + ".", points,
            r.get("causal_evidence") or [])

    # D
    points, evidence = [], []
    gap_point = False
    if r["gap_expected"] and structured and r.get("has_introduction"):
        if not r["gap_assessed"]:
            points.append("The gap statement was not assessed: that check "
                          "is off.")
        elif r["gap_present"] and r["gap_evidence"]:
            points.append("A gap statement was detected: the reader is told "
                          "what was missing before this work.")
            evidence.append(r["gap_evidence"])
        else:
            gap_point = True
            points.append("No gap statement was detected in the "
                          "introduction: the reader may not be told what was "
                          "missing before this work.")
    points.append(f"Calibration: {m['hedge_booster_balance']} (hedges "
                  f"{m['hedges_per_100w']} per 100 words against boosters "
                  f"{m['boosters_per_100w']}).")
    if r["overclaims"]:
        points.append(_count(r["overclaims"], "overclaiming verb",
                             "overclaiming verbs")
                      + " such as 'prove' or 'conclusively': reserve strong "
                      "verbs for strong evidence.")
    if r["hedge_stacks"]:
        points.append(_count(r["hedge_stacks"], "stacked hedge",
                             "stacked hedges")
                      + ": one calibrated qualifier beats two weak ones.")
    if r["novelty_risks"]:
        points.append(_count(r["novelty_risks"], "absolute novelty claim",
                             "absolute novelty claims")
                      + ": soften with 'to our knowledge' and cite the "
                      "nearest work.")
    no_limits = False
    if r["limitations_expected"] and structured:
        if r["has_limitations"]:
            points.append("A limitations section is present, so the "
                          "rebuttal is pre-empted.")
        else:
            no_limits = True
            points.append("No limitations section was found: the reviewer "
                          "may supply the rebuttal instead.")
    links = (r.get("argument") or {}).get("missing_links") or []
    for link in links[:6]:
        points.append(f"Argument: {link['message']}")
    if r["abstract_missing"]:
        points.append("Abstract: " + r["abstract_missing"][0])
    if r["expected_missing"] and structured:
        points.append("Sections a reader of this kind of document expects "
                      "but the headings do not show: "
                      + ", ".join(r["expected_missing"]) + ".")
    if r["not_assessed"]:
        points.append("Not assessed (checks that are off): "
                      + ", ".join(_short(x) for x in r["not_assessed"]))
    worries = (r["overclaims"] + r["hedge_stacks"] + r["novelty_risks"]
               + len(links) + int(gap_point) + int(no_limits))
    if not r.get("claims_seen") and worries == 0:
        add("D", "not_applicable",
            "No claims were detected to weigh in this text.", points,
            evidence)
    elif worries == 0:
        add("D", "not_detected",
            "Nothing detected weakens the claims. That is not a judgement "
            "that they are sound.", points, evidence)
    else:
        add("D", "detected",
            _count(worries, "thing was", "things were")
            + " detected that may weaken the claims; see the points.",
            points, evidence)

    # E
    if r["significance"]["present"]:
        add("E", "detected", "The significance is stated.",
            evidence=[r["significance"]["evidence"]])
    else:
        add("E", "not_detected",
            "No explicit statement of what a reader can do with this was "
            "detected.",
            ["Does the ending widen back out? Say what should change in the "
             "field or in practice, and for whom."])
    return out


def render_review(r: dict) -> str:
    """Plain-text brief for the CLI and the old local add-in."""
    m = r["metrics"]
    L: list[str] = []
    add = L.append
    add("REVIEWER'S BRIEF — the critical reader's five questions")
    add(f"sections detected: {', '.join(r['sections'])} · "
        f"{m['words']} words · {r['total_suggestions']} suggestions total")
    for q in r["questions"]:
        add("")
        add(f"{q['id']}. {q['question']}")
        add(f"   {q['verdict']}")
        for p in q["points"]:
            add(f"     - {p}")
        for e in q["evidence"]:
            add(f'     "{e}"')
    if r["top_rules"]:
        add("")
        add("Most frequent checks: "
            + ", ".join(f"{t['short']} ({t['count']})"
                        for t in r["top_rules"]))
    add(r.get("disclaimer", DISCLAIMER))
    add("Source: " + r["source"])
    return "\n".join(L)
