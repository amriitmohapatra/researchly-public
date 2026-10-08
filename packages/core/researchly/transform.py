"""Deterministic sentence/paragraph rewriting — "polish".

One click composes every SAFE, rule-derived edit into a rewritten passage
with a word-level diff and a per-edit explanation. No LLM anywhere: every
change is traceable to a named rule from the writing guide, reproducible,
and cannot invent content — which also means equations, citations, numbers,
and technical terms are structurally incapable of being altered (edits only
ever touch spans a rule explicitly matched; markup is masked besides).

What polish applies (concrete-replacement edits only):
  W201 grand words · W202 wordy phrases · W205 filler deletion ·
  W206 redundant pairs · W207 doubled words · G102 buried actions
  (conjugated in place) · G105 expletive-opener restructuring.

What polish deliberately does NOT do: convention prompts (C3xx) and
judgment calls (passive voice, hedge choice, sentence splits) stay as
flags for the author — the guide's own position is that these depend on
what belongs in the topic position, which is the author's call.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .document import Document
from .engine import REGISTRY, check

# Rules whose replacements are safe to auto-compose.
POLISH_RULES = {"W201", "W202", "W205", "W206", "W207", "G102"}


@dataclass
class Edit:
    rule_id: str
    rule_name: str
    before: str
    after: str
    why_short: str


@dataclass
class PolishResult:
    original: str
    rewritten: str
    segments: list = field(default_factory=list)   # [{op, text}]
    edits: list = field(default_factory=list)      # [Edit as dict]
    notes: list = field(default_factory=list)      # non-applied observations
    changed: bool = False

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "rewritten": self.rewritten,
            "segments": self.segments,
            "edits": self.edits,
            "notes": self.notes,
            "changed": self.changed,
        }


# ---------------------------------------------------------------------------
# Expletive-opener restructuring (G105 as a transform)
# ---------------------------------------------------------------------------

_EXPLETIVE_RX = re.compile(
    r"^(?P<lead>\s*)There\s+(?:is|are|was|were)\s+"
    r"(?P<np>[^,;.]{3,80}?)\s+(?:that|which|who)\s+",
    re.IGNORECASE)


def _expletive_edits(masked: str,
                     original: str) -> list[tuple[int, int, str, str]]:
    """(start, end, replacement, before) spans rewriting 'There are X that
    VERB…' → 'X VERB…', per sentence, conservative pattern only.

    The pattern is matched against `masked` so markup cannot trip the regex,
    but the replacement is cut from `original` and any match whose span
    covers a masked region is DROPPED.

    Both halves matter. Masked regions are runs of spaces, so `\\s+` in the
    pattern happily swallows one: in "There are $n$ parameters that vary"
    the match spans the maths even though the noun phrase does not, and
    rewriting the span deleted it — output "Parameters vary". The same
    swallowed "[@smith2020]" out of a citation. Polish promises that
    equations and citations cannot be altered; a rewrite that cannot keep
    that promise must decline, not approximate.
    """
    out = []
    for sent_m in re.finditer(r"[^.!?\n]+[.!?]?", masked):
        sent = sent_m.group(0)
        m = _EXPLETIVE_RX.match(sent)
        if not m:
            continue
        start = sent_m.start() + m.start()
        end = sent_m.start() + m.end()
        # masked[i] != original[i] exactly where markup was blanked out.
        if masked[start:end] != original[start:end]:
            continue
        np = original[sent_m.start() + m.start("np"):
                      sent_m.start() + m.end("np")].strip()
        if not np:
            continue
        replacement = m.group("lead") + np[0].upper() + np[1:] + " "
        out.append((start, end, replacement, original[start:end]))
    return out


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def polish(text: str, nlp, kind: str = "plain",
           disabled: set[str] | None = None) -> PolishResult:
    """Iterate single passes to a fixpoint (max 3): one edit can reveal
    another — deleting 'It is important to note that ' exposes 'There are
    three factors that drive…' for the expletive transform."""
    current = text
    all_edits: list[dict] = []
    notes: list[str] = []
    for i in range(3):
        step = _polish_once(current, nlp, kind, disabled)
        if i == 0:
            notes = step.notes
        if not step.changed:
            break
        all_edits.extend(step.edits)
        current = step.rewritten
    return PolishResult(
        original=text,
        rewritten=current,
        segments=_diff_segments(text, current),
        edits=all_edits,
        notes=notes,
        changed=(current != text),
    )


def _polish_once(text: str, nlp, kind: str = "plain",
                 disabled: set[str] | None = None) -> PolishResult:
    doc = Document.from_text(text, kind)
    suggestions = check(doc, nlp, disabled=disabled or set(),
                        show_preferences=False)

    spans: list[tuple[int, int, str, str, str]] = []  # start,end,repl,rule,before
    notes: list[str] = []
    for s in suggestions:
        if s.rule_id in POLISH_RULES and s.replacement is not None:
            spans.append((s.start, s.end, s.replacement, s.rule_id, s.text))
        else:
            notes.append(f"{s.rule_id} {s.rule_name} (§{s.section}): "
                         f"{s.message}")

    for start, end, repl, before in _expletive_edits(doc.masked, doc.original):
        spans.append((start, end, repl, "G105", before))

    # apply non-overlapping, left to right (first wins on overlap)
    spans.sort(key=lambda x: (x[0], -(x[1])))
    applied: list[tuple[int, int, str, str, str]] = []
    last_end = -1
    for sp in spans:
        if sp[0] >= last_end:
            applied.append(sp)
            last_end = sp[1]

    out: list[str] = []
    pos = 0
    edits: list[Edit] = []
    for start, end, repl, rule_id, before in applied:
        out.append(text[pos:start])
        seg = repl
        if seg == "":
            # deletions absorb one following space so words don't collide
            if end < len(text) and text[end] == " ":
                end += 1
            # deletion at a sentence start: capitalize what now leads
            at_start = (start == 0
                        or text[max(0, start - 2):start] in {". ", "! ", "? "}
                        or text[:start].endswith("\n"))
            if at_start and end < len(text) and text[end].islower():
                seg = text[end].upper()
                end += 1
        out.append(seg)
        pos = end
        rule = REGISTRY.get(rule_id)
        edits.append(Edit(
            rule_id=rule_id,
            rule_name=rule.name if rule else rule_id,
            before=" ".join(before.split()),
            after=repl if repl else "(deleted)",
            why_short=rule.short if rule else ""))
    out.append(text[pos:])
    rewritten = "".join(out)
    if applied:                      # never touch text we didn't edit
        rewritten = _repair(rewritten)

    result = PolishResult(
        original=text,
        rewritten=rewritten,
        segments=_diff_segments(text, rewritten),
        edits=[e.__dict__ for e in edits],
        notes=notes[:12],
        changed=(rewritten != text),
    )
    return result


def _repair(text: str) -> str:
    """Post-edit punctuation cleanup. Deliberately narrow: these sequences
    (space before punctuation, doubled commas) essentially never occur in
    legitimate prose, so fixing them globally cannot corrupt untouched
    text — unlike blanket double-space collapsing or re-capitalization,
    which could alter the author's own formatting."""
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    return text


def _diff_segments(a: str, b: str) -> list[dict]:
    """Word-level diff as renderable segments [{op: eq|del|ins, text}]."""
    ta = re.findall(r"\S+|\s+", a)
    tb = re.findall(r"\S+|\s+", b)
    sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
    segs: list[dict] = []

    def push(op: str, text: str):
        if not text:
            return
        if segs and segs[-1]["op"] == op:
            segs[-1]["text"] += text
        else:
            segs.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("eq", "".join(ta[i1:i2]))
        elif tag == "delete":
            push("del", "".join(ta[i1:i2]))
        elif tag == "insert":
            push("ins", "".join(tb[j1:j2]))
        else:  # replace
            push("del", "".join(ta[i1:i2]))
            push("ins", "".join(tb[j1:j2]))
    return segs
