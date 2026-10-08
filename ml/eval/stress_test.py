"""Stress-test Researchly against professionally edited scientific prose.

Two measurements the project has never had:

1. FALSE-POSITIVE RATE on publication-quality text. The `after` side of AESW
   is what a professional language editor signed off on. Anything Researchly
   flags there is a candidate false positive — a stronger oracle than the
   accepted-thesis corpus, because it is post-editing and free of PDF
   extraction damage.

2. DETECTION RATE on text a human expert did change. The `before` side of an
   edited sentence is known to need work. Whether Researchly says anything,
   and whether it says it *at the place the editor changed*, is the first
   recall signal this codebase has produced.

Neither number is a GEC F0.5 score — AESW edits are copy-editing decisions,
not only grammatical errors, and many are house style Researchly should not
imitate. Read them as coverage indicators, not as accuracy.

Usage:
    python3.10 eval/stress_test.py [--limit N] [--disable IDS]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "packages" / "core"))

from eval.aesw import iter_sentences                      # noqa: E402
from researchly import api                                # noqa: E402
from researchly.config import Config                      # noqa: E402
from researchly.document import Document                  # noqa: E402
from researchly.engine import Category, check             # noqa: E402

DATA = HERE / "data" / "aesw_dev.xml"


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=4000,
                    help="sentences to evaluate (default 4000)")
    ap.add_argument("--disable", default="",
                    help="comma-separated rule ids to mute")
    ap.add_argument("--data", default=str(DATA))
    args = ap.parse_args()

    path = Path(args.data)
    if not path.exists():
        print(f"missing corpus: {path}\n"
              f"see docs/eval-corpora.md for the download step",
              file=sys.stderr)
        return 2

    disabled = {r.strip() for r in args.disable.split(",") if r.strip()}
    cfg = Config(disabled=disabled, show_preferences=False)
    nlp = api.get_nlp()

    clean_words = clean_flags = clean_sents = clean_hit = 0
    bad_sents = bad_hit = bad_at_site = 0
    clean_by_rule: Counter = Counter()
    hit_by_rule: Counter = Counter()
    samples: list[tuple[str, str, str]] = []

    for s in iter_sentences(path, limit=args.limit):
        # (1) the editor-approved version — everything flagged here is suspect
        doc_after = Document.from_text(s.after, "markdown")
        doc_after.config = cfg
        doc_after.extra_dictionary = []
        after_flags = check(doc_after, nlp, disabled=disabled,
                            show_preferences=False)
        clean_sents += 1
        clean_words += len(s.after.split())
        clean_flags += len(after_flags)
        if after_flags:
            clean_hit += 1
        for f in after_flags:
            clean_by_rule[f.rule_id] += 1
            if len(samples) < 400:
                samples.append((f.rule_id, f.text, s.after))

        # (2) the pre-edit version of sentences an expert actually changed
        if not s.was_edited:
            continue
        doc_before = Document.from_text(s.before, "markdown")
        doc_before.config = cfg
        doc_before.extra_dictionary = []
        before_flags = check(doc_before, nlp, disabled=disabled,
                             show_preferences=False)
        bad_sents += 1
        if before_flags:
            bad_hit += 1
            for f in before_flags:
                hit_by_rule[f.rule_id] += 1
        if any(overlaps((f.start, f.end), sp)
               for f in before_flags for sp in s.edit_spans):
            bad_at_site += 1

    print("=" * 72)
    print("AESW 2016 dev — professionally edited scientific prose")
    print("=" * 72)
    print(f"\n1. FALSE POSITIVES on editor-approved text")
    print(f"   sentences               {clean_sents:>8,}")
    print(f"   words                   {clean_words:>8,}")
    print(f"   flags                   {clean_flags:>8,}")
    rate = clean_flags / clean_words * 1000 if clean_words else 0
    print(f"   flags per 1000 words    {rate:>8.1f}"
          f"   <- thesis corpus baseline 10.4")
    pct = clean_hit / clean_sents * 100 if clean_sents else 0
    print(f"   sentences with >=1 flag {pct:>7.1f}%")
    print("\n   top rules firing on published prose:")
    for rid, n in clean_by_rule.most_common(12):
        print(f"     {rid:8s} {n:6,}  ({n / clean_flags * 100:4.1f}%)")

    print(f"\n2. DETECTION on text an expert did change")
    print(f"   edited sentences        {bad_sents:>8,}")
    hp = bad_hit / bad_sents * 100 if bad_sents else 0
    sp = bad_at_site / bad_sents * 100 if bad_sents else 0
    print(f"   flagged something       {hp:>7.1f}%")
    print(f"   flagged AT the edit     {sp:>7.1f}%   <- the honest recall")
    print("\n   rules firing on pre-edit text:")
    for rid, n in hit_by_rule.most_common(10):
        print(f"     {rid:8s} {n:6,}")

    print("\n3. SAMPLE false positives (flagged in published prose)")
    seen: set = set()
    for rid, text, sent in samples:
        if rid in seen:
            continue
        seen.add(rid)
        short = " ".join(sent.split())[:110]
        print(f"\n   [{rid}] flagged {text!r}")
        print(f"        {short}")
        if len(seen) >= 8:
            break
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
