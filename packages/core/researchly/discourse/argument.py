"""The argument object — Toulmin-structured document intelligence (W4).

The Codex review's core observation (§B): the next modelling unit for
Researchly is not another phrase rule but an ARGUMENT OBJECT — claim,
grounds, warrant, qualifier, rebuttal — because the highest-value feedback
is not "better wording" but "this paragraph makes a claim and never
warrants why the evidence supports it".

This module is deterministic and label-only:

- sentences get argument ROLES from signal lexicons (claim, evidence,
  warrant, limitation, rebuttal, background, method, result, contribution,
  implication) — the same technique as abstract_lens, which it reuses;
- per section, roles assemble into an `ArgumentObject` whose
  `missing_links` are reader-facing diagnostics ("claim without warrant",
  "evidence without interpretation", "limitation not reflected in claim
  strength");
- nothing here rewrites text, registers a rule, or changes any surface's
  output. The lenses consume these signals explicitly (sprint item 10);
  a future argument-role *classifier* (Phase 2 of the brief) slots in by
  replacing `label_sentence` while every consumer stays unchanged.

Design note on confidence: lexicon matches are precise but shallow, so
every role carries the matched signal as its evidence and a flat, honest
confidence. When a learned classifier replaces the lexicons, the same
fields carry its calibrated scores.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Optional

from ..document import Document

ROLES = ("claim", "evidence", "warrant", "qualifier", "limitation",
         "rebuttal", "background", "method", "result", "contribution",
         "implication")

# Signal lexicons. Order matters within a role list (first match wins as
# evidence); order across roles is resolved by _ROLE_PRIORITY below.
_SIGNALS: dict[str, list[str]] = {
    "limitation": [
        r"\blimitations?\b", r"\bwe (could|can) ?not\b",
        r"\bwe were unable to\b", r"\bcaution\b", r"\bcaveats?\b",
        r"\bshould be interpreted (with|in light)\b",
        r"\bmay not (generali[sz]e|apply|hold|capture)\b",
        r"\bis (subject|prone) to\b.*\bbias\b", r"\bunmeasured\b",
        r"\bresidual confounding\b", r"\bsmall sample\b",
        r"\bdata (were|was|are|is) not available\b",
    ],
    "rebuttal": [
        r"\bone might (argue|object|expect)\b", r"\bit could be argued\b",
        r"\ban alternative explanation\b", r"\bcontrary to\b",
        r"\bhowever, .*\b(not|cannot|unlikely)\b",
        r"\bthis does not (imply|mean|establish)\b",
    ],
    "warrant": [
        r"\bbecause\b", r"\bsince\b.*\b(we|this|these|it)\b",
        r"\bthis (suggests?|indicates?|implies|means) that\b",
        r"\bconsistent with\b", r"\bin line with\b",
        r"\bas (expected|predicted) (from|by|under)\b",
        r"\bwhich (explains?|accounts? for|supports?)\b",
        r"\bunder (the|this|these) assumptions?\b",
        r"\btherefore\b", r"\bhence\b", r"\bthus\b",
    ],
    "qualifier": [
        r"\bmay\b", r"\bmight\b", r"\bcould\b", r"\bappears? to\b",
        r"\bseems? to\b", r"\bis likely to\b", r"\bprobably\b",
        r"\bto some extent\b", r"\bin (most|some) (cases|settings)\b",
        r"\bconditional on\b", r"\bif .* holds?\b",
    ],
    "contribution": [
        r"\b(our|this|the) (study|paper|thesis|work|analysis) "
        r"(contributes?|adds?|extends?|provides?|offers?|advances?)\b",
        r"\bto (our|the best of our) knowledge\b",
        r"\bfor the first time\b", r"\bnovel\b",
        r"\bfills? (a|an|this|the) gap\b",
        r"\bstrengths? of (this|our) (study|approach)\b",
    ],
    "implication": [
        r"\bimplications?\b",
        r"\binform(s|ing)? (policy|practice|decision|planning|control|"
        r"surveillance|guidelines)\b",
        r"\b(policymakers|clinicians|public health|practitioners)"
        r" (could|can|should|may|need)\b",
        r"\bfuture (research|studies|work) (should|could|is needed)\b",
        r"\bthese (findings|results) (suggest|highlight|underscore) "
        r"the (need|importance|value)\b",
    ],
    "result": [
        r"\bwe (found|find|observed|estimate[d]? that|identified)\b",
        r"\bresults? (show|showed|indicate[d]?|reveal(ed)?)\b",
        r"\bwas (significantly )?(associated|correlated|linked)\b",
        r"\b95\s?% (ci|cri|credible|confidence)\b",
        r"\b(odds|risk|hazard|rate) ratio\b",
        r"\b(increased|decreased|reduced|higher|lower) (than|by|among|in)\b",
    ],
    "method": [
        r"\bwe (used|use|fitted|fit|conducted|developed|applied|"
        r"analy[sz]ed|model(led|ed)|simulated|estimated|calibrated|"
        r"implemented|assumed)\b",
        r"\bdata (from|were|was)\b",
        r"\b(seir|sir|compartmental|branching process|regression|"
        r"agent-based|transmission) model\b",
        r"\bwere (recruited|collected|included|enrolled|randomi[sz]ed)\b",
        r"\bpriors? (were|was|on)\b", r"\blikelihood\b",
        r"\bsensitivity analys[ie]s\b",
    ],
    "claim": [
        r"\bwe (argue|contend|propose|conclude|claim|maintain)\b",
        r"\b(demonstrates?|establishes?|proves?|confirms?) that\b",
        # verb forms only — bare "cause"/"causes?" also matches the noun in
        # "a leading cause of", which is background prose, not a claim
        r"\b(causes|caused|drives|drove|leads to|led to|results in|"
        r"reduces|increases|prevents|explains)\b",
        r"\bis (essential|critical|necessary|key|central) (to|for)\b",
        r"\b(should|must) (be|not)\b",
    ],
    "evidence": [
        r"\b\d+(\.\d+)?\s?%", r"\bp\s?[<=>]\s?0?\.\d+\b",
        r"\bn\s?=\s?\d+", r"\btable \d+\b", r"\bfigure \d+\b",
        r"\bet al\b", r"\((19|20)\d{2}\)", r"\[\d+([,–-]\s?\d+)*\]",
        r"\bpreviously (reported|shown|estimated)\b",
        r"\bin (a|an|the) (previous|prior|earlier) (study|analysis)\b",
    ],
    "background": [
        r"\bis (a|an|the) (leading|major|common|important)\b",
        r"\bhas been (widely|extensively) (studied|used|reported)\b",
        r"\bit is (well[- ])?(known|established|recognised|recognized)\b",
        r"\bremains? (a|an|the)\b.*\b(burden|challenge|threat)\b",
        r"\bworldwide\b", r"\bglobally\b", r"\beach year\b",
    ],
}

# When several roles match one sentence, the most *argumentative* reading
# wins — a sentence that both hedges and claims is a qualified claim, and
# the claim is what the reader has to be able to follow.
_ROLE_PRIORITY = ("limitation", "rebuttal", "contribution", "implication",
                  "warrant", "claim", "result", "method", "evidence",
                  "qualifier", "background")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SentenceRole:
    """One sentence, one primary argument role, with its evidence."""
    start: int                   # char offsets into the ORIGINAL text
    end: int
    role: str                    # one of ROLES, or "other"
    signal: str = ""             # the lexicon pattern that matched
    all_roles: tuple = ()        # every role that matched, primary first
    confidence: float = 0.6      # flat and honest for lexicon matching

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "role": self.role,
                "signal": self.signal, "all_roles": list(self.all_roles),
                "confidence": self.confidence}


@dataclass
class ArgumentObject:
    """Toulmin-shaped skeleton of one section's argument (sprint item 9).

    Field values are sentence spans (start, end) into the original text —
    never rewritten prose. `missing_links` is the reader-facing output:
    each entry is a (code, message) the lenses can surface verbatim.
    """
    section: str = "unknown"
    claim: list = field(default_factory=list)
    evidence_or_grounds: list = field(default_factory=list)
    warrant: list = field(default_factory=list)
    qualifier: list = field(default_factory=list)
    limitation_or_rebuttal: list = field(default_factory=list)
    contribution: list = field(default_factory=list)
    confidence: float = 0.6
    supporting_spans: list = field(default_factory=list)   # SentenceRole
    missing_links: list = field(default_factory=list)      # (code, message)
    link_spans: dict = field(default_factory=dict)         # code -> spans

    def to_dict(self) -> dict:
        return {
            "section": self.section,
            "claim": self.claim,
            "evidence_or_grounds": self.evidence_or_grounds,
            "warrant": self.warrant,
            "qualifier": self.qualifier,
            "limitation_or_rebuttal": self.limitation_or_rebuttal,
            "contribution": self.contribution,
            "confidence": self.confidence,
            "supporting_spans": [r.to_dict() for r in self.supporting_spans],
            "missing_links": [{"code": c, "message": m}
                              for c, m in self.missing_links],
        }


def label_sentence(sentence: str) -> tuple[str, str, tuple]:
    """(primary_role, matched_signal, all_roles) for one sentence.

    The single replacement point for a future learned classifier: swap this
    function, keep every consumer.
    """
    matched: dict[str, str] = {}
    for role in _ROLE_PRIORITY:
        for rx in _SIGNALS[role]:
            if re.search(rx, sentence, re.IGNORECASE):
                matched[role] = rx
                break
    if not matched:
        return "other", "", ()
    ordered = tuple(r for r in _ROLE_PRIORITY if r in matched)
    primary = ordered[0]
    return primary, matched[primary], ordered


def label_sentences(document: Document, spacy_doc=None) -> list[SentenceRole]:
    """Role-label every sentence, with original-text offsets.

    With `spacy_doc` (the shared parse, api.analyze) the sentences are the
    parser's, so abbreviations, decimals, equations and blank-line
    boundaries split exactly as everywhere else (Codex review R5). Without
    it, a punctuation split over the MASKED text (offsets survive markup;
    masked regions are spaces the lexicons do not match).
    """
    out: list[SentenceRole] = []
    if spacy_doc is not None:
        for sent in spacy_doc.sents:
            chunk = sent.text
            if not chunk.strip() or document.in_table(sent.start_char):
                continue
            role, signal, all_roles = label_sentence(chunk)
            out.append(SentenceRole(start=sent.start_char, end=sent.end_char,
                                    role=role, signal=signal,
                                    all_roles=all_roles))
        return out
    text = document.masked
    pos = 0
    for chunk in _SENT_SPLIT.split(text):
        if not chunk.strip():
            pos += len(chunk) + 1
            continue
        start = text.find(chunk, pos)
        if start == -1:
            pos += len(chunk) + 1
            continue
        end = start + len(chunk)
        pos = end
        # A masked heading before the sentence is spaces: start at the words.
        start += len(chunk) - len(chunk.lstrip())
        role, signal, all_roles = label_sentence(chunk)
        out.append(SentenceRole(start=start, end=end, role=role,
                                signal=signal, all_roles=all_roles))
    return out


# --- diagnostics -----------------------------------------------------------

# Sections where a claim is *expected* to be warranted in place. Methods
# narrate; Results report; the argumentative load sits here.
_ARGUMENTATIVE = {"discussion", "conclusion", "abstract", "introduction",
                  "limitations", "unknown", "front", "other"}


def _near(spans: list, i: int, roles: tuple, k: int) -> bool:
    lo, hi = max(0, i - k), min(len(spans), i + k + 1)
    return any(set(roles) & set(spans[j].all_roles) for j in range(lo, hi))


def _diagnose(obj: ArgumentObject) -> list:
    """Missing-link diagnostics for one section instance.

    A claim is linked to a warrant only by its own sentence or the next or
    previous one, and to grounds within two sentences: an unrelated
    "because" elsewhere in the section no longer satisfies it (Codex review
    R5). The wording says what could not be linked, never that the
    evidence does not exist: the signals are lexicons, not understanding.
    """
    links: list = []
    spans = obj.supporting_spans
    name = obj.section.capitalize()
    argumentative = obj.section in _ARGUMENTATIVE
    claims = [i for i, r in enumerate(spans) if "claim" in r.all_roles]
    unwarranted = [i for i in claims if not _near(spans, i, ("warrant",), 1)]
    ungrounded = [i for i in claims
                  if not _near(spans, i, ("evidence", "result"), 2)]

    def add(code, message, idx):
        links.append((code, message))
        obj.link_spans[code] = [(spans[i].start, spans[i].end) for i in idx]

    if argumentative and unwarranted:
        n = len(unwarranted)
        add("claim_without_warrant",
            f"{n} claim{'s' if n != 1 else ''} in the {name} could not be "
            "linked to a reason nearby: no 'because', 'this suggests that' "
            "or 'consistent with' in the same or the next sentence. Say why "
            "the evidence supports the claim.", unwarranted)
    if argumentative and ungrounded:
        n = len(ungrounded)
        add("claim_without_grounds",
            f"{n} claim{'s' if n != 1 else ''} in the {name} could not be "
            "linked to evidence nearby: no number, citation or reported "
            "finding within two sentences. What does each claim stand on?",
            ungrounded)
    if obj.section in ("results", "discussion") \
            and obj.evidence_or_grounds and not obj.warrant and not claims:
        add("evidence_without_interpretation",
            f"The {name} reports results, but no sentence was detected that "
            "says what they mean. What should the reader conclude?",
            [i for i, r in enumerate(spans)
             if r.role in ("evidence", "result")][:3])
    if obj.limitation_or_rebuttal and claims and not obj.qualifier:
        add("limitation_not_reflected_in_claim_strength",
            f"The {name} states a limitation, but its claims carry no "
            "qualifier ('may', 'likely', 'under these assumptions'). Let the "
            "limitation show in how strongly the claims are made.", claims)
    if obj.section in ("discussion", "conclusion") and not obj.contribution:
        links.append(("contribution_unclear",
                      f"No sentence in the {name} was detected that says "
                      "what this work adds to the field."))
        obj.link_spans["contribution_unclear"] = []
    return links


def build_argument(document: Document, roles: Optional[list] = None,
                   spacy_doc=None) -> list[ArgumentObject]:
    """One ArgumentObject per detected section (sprint item 9).

    Pure analysis: no rules registered, no suggestions emitted, no text
    changed. Consumers (review lens; later the Reviewer mode) decide what
    to surface.
    """
    roles = roles if roles is not None else label_sentences(document,
                                                            spacy_doc)
    # One object per section INSTANCE (the heading that governs it), so two
    # Discussion chapters are never pooled into one bucket (review R5).
    starts = [h.start for h in document.headings]
    by_section: dict = {}
    for r in roles:
        section = document.section_at(r.start)
        k = bisect_right(starts, r.start) - 1
        key = (section, starts[k] if k >= 0 else -1)
        obj = by_section.setdefault(key, ArgumentObject(section=section))
        obj.supporting_spans.append(r)
        span = (r.start, r.end)
        if r.role == "claim":
            obj.claim.append(span)
        elif r.role in ("evidence", "result"):
            obj.evidence_or_grounds.append(span)
        elif r.role == "warrant":
            obj.warrant.append(span)
        elif r.role == "qualifier":
            obj.qualifier.append(span)
        elif r.role in ("limitation", "rebuttal"):
            obj.limitation_or_rebuttal.append(span)
        elif r.role == "contribution":
            obj.contribution.append(span)
        # secondary roles still inform the qualifier field: a qualified
        # claim counts as both
        if r.role != "qualifier" and "qualifier" in r.all_roles:
            obj.qualifier.append(span)

    out = []
    for obj in by_section.values():
        obj.missing_links = _diagnose(obj)
        out.append(obj)
    out.sort(key=lambda o: (o.supporting_spans[0].start
                            if o.supporting_spans else 0))
    return out


# Small helper used by _diagnose, defined on the class after the fact so
# the dataclass body stays a plain field list (3.10-friendly).
def _supporting_spans_have(self, role: str) -> bool:
    return any(r.role == role for r in self.supporting_spans)


ArgumentObject.supporting_spans_have = _supporting_spans_have


def summarize(objects: list) -> dict:
    """Compact cross-section summary for the review lens (sprint item 10)."""
    all_links = [(o.section, c, m, o.link_spans.get(c, []))
                 for o in objects for c, m in o.missing_links]
    role_counts: dict[str, int] = {}
    for o in objects:
        for r in o.supporting_spans:
            role_counts[r.role] = role_counts.get(r.role, 0) + 1
    return {
        "sections": [o.section for o in objects],
        "role_counts": role_counts,
        "missing_links": [{"section": s, "code": c, "message": m,
                           "spans": [list(x) for x in sp]}
                          for s, c, m, sp in all_links],
    }
