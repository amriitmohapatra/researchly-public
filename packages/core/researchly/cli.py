"""Researchly CLI.

Usage:
  python -m researchly check FILE [FILE...] [options]
      (.tex .md .qmd .Rmd .txt, Word .docx, Overleaf project .zip)
  python -m researchly rules
  python -m researchly explain RULE_ID

Options for `check`:
  --all            also show Preference suggestions (hidden by default)
  --explain        print the full "why" under every suggestion
  --json           machine-readable output (suggestions + metrics)
  --disable IDS    comma-separated rule ids to mute (e.g. G106,W203)
  --no-metrics     skip the document metrics read-out
Muting can also live in a `.researchly.toml` next to the file or in the
working directory:

  [rules]
  disable = ["W203", "G106"]
  show_preferences = false
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .document import Document
from .engine import REGISTRY, Category, check
from . import api
from . import config as config_mod
from . import metrics as metrics_mod
from .health import summary_line
from .ingest import IngestError, source_position

# --- ANSI ----------------------------------------------------------------

COLORS = {
    Category.CORRECTION: "\033[31m",    # red
    Category.IMPROVEMENT: "\033[34m",   # blue
    Category.CONVENTION: "\033[33m",    # yellow
    Category.PREFERENCE: "\033[35m",    # magenta
}
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


def _use_color() -> bool:
    return sys.stdout.isatty()


def _c(code: str, s: str) -> str:
    return f"{code}{s}{RESET}" if _use_color() else s


# --- config ----------------------------------------------------------------

def _get_toml_loader():
    """tomllib is stdlib from Python 3.11; fall back to tomli on older."""
    try:
        import tomllib
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli
            return tomli
        except ModuleNotFoundError:
            return None


def load_config(near: Path) -> dict:
    """Back-compat shim: the raw TOML mapping for the file governing `near`.

    Settings now live in `researchly.config`, which layers the user config
    under the project one and is read by every surface. Kept so existing
    callers keep working; new code should use `config.load()`.
    """
    path = config_mod.project_config_path(near)
    return config_mod._read_toml(path) if path else {}


# --- nlp -------------------------------------------------------------------

def get_nlp():
    """Shared with every other surface — including the raised max_length.

    The CLI was previously the only surface that did NOT raise spaCy's
    1,000,000-character cap, so `researchly check` alone raised on a long
    thesis while the same document worked in Word.
    """
    return api.get_nlp()


# --- commands --------------------------------------------------------------

def cmd_check(args) -> int:
    nlp = get_nlp()
    exit_code = 0
    payload = []

    for fname in args.files:
        path = Path(fname)
        if not path.exists():
            print(f"researchly: no such file: {fname}", file=sys.stderr)
            return 2
        cfg = config_mod.load(path)
        if args.disable:
            cfg.disabled |= {x.strip() for x in args.disable.split(",")
                             if x.strip()}
        if args.all:
            cfg.show_preferences = True
        if args.mode:
            cfg.mode = args.mode

        try:
            # .docx and Overleaf .zip are read by researchly.ingest, the
            # same adapters the hosted engine uses.
            a = api.analyze(path, nlp=nlp, cfg=cfg,
                            with_metrics=not args.no_metrics)
        except IngestError as e:
            # One unreadable file must not discard the others' results.
            print(f"researchly: {fname}: {e.message}", file=sys.stderr)
            exit_code = 2
            continue
        suggestions, document = a.suggestions, a.document

        if args.json:
            items = [s.to_dict() for s in suggestions]
            if len(document.segments) > 1:
                # line/col index the combined project text; say where each
                # suggestion is in the file that holds it.
                for d, s in zip(items, suggestions):
                    src, line, col = source_position(
                        document.segments, document.original, s.start)
                    d["source"] = {"path": src, "line": line, "col": col}
            payload.append({
                "file": str(path),
                "warnings": list(document.warnings),
                "suggestions": items,
                "hidden_preferences": a.hidden_preferences,
                "hidden_by_mode": a.hidden_by_mode,
                "mode": a.config.mode,
                "metrics": a.metrics.to_dict() if a.metrics else None,
                "health": [t.to_dict() for t in a.health],
            })
        else:
            _render(path, document, suggestions,
                    hidden_prefs=a.hidden_preferences,
                    hidden_by_mode=a.hidden_by_mode,
                    metrics=a.metrics, explain=args.explain, health=a.health)
        if suggestions:
            exit_code = max(exit_code, 1)

    if args.json:
        print(json.dumps(payload, indent=2))
    return exit_code


def _render(path, document, suggestions, *, hidden_prefs, metrics, explain,
            health=None, hidden_by_mode=0):
    counts = {}
    for s in suggestions:
        counts[s.category] = counts.get(s.category, 0) + 1
    summary = ", ".join(
        f"{n} {cat.value}{'s' if n != 1 else ''}"
        for cat, n in sorted(counts.items(), key=lambda kv: kv[0].value))
    header = f"{BOLD}{path}{RESET}" if _use_color() else str(path)
    print(f"\n{header} — {len(suggestions)} suggestion"
          f"{'s' if len(suggestions) != 1 else ''}"
          + (f" ({summary})" if summary else ""))
    if hidden_prefs:
        print(_c(DIM, f"  ({hidden_prefs} preference suggestion"
                      f"{'s' if hidden_prefs != 1 else ''} hidden — "
                      "--all to show)"))
    if hidden_by_mode:
        print(_c(DIM, f"  (Draft mode: {hidden_by_mode} document-level "
                      f"suggestion{'s' if hidden_by_mode != 1 else ''} held "
                      "back — --mode revise to show)"))
    # Say which tiers did NOT run. Without this, a dead grammar engine and
    # clean prose produce identical output.
    for tier in (health or []):
        if not tier.ok and (tier.remedy or tier.state in ("disabled",
                                                          "error")):
            note = f"  ! {tier.label} checking is OFF — {tier.detail}"
            if tier.remedy:
                note += f"\n    fix: {tier.remedy}"
            print(_c(COLORS[Category.CONVENTION], note))
    for w in document.warnings:
        print(_c(COLORS[Category.CONVENTION], f"  ! {w}"))

    for s in suggestions:
        tag = _c(COLORS[s.category], f"[{s.category.value}]")
        loc = f"L{s.line}:{s.col}"
        if len(document.segments) > 1:
            # An Overleaf project: point into the file the text came from.
            src, line, col = source_position(document.segments,
                                             document.original, s.start)
            loc = f"{src}:{line}:{col}"
        sec = f" §{s.section}" if s.section not in ("unknown",) else ""
        print(f"\n  {loc} {tag} {s.rule_id} {s.rule_name}{_c(DIM, sec)}")
        snippet = " ".join(s.text.split())
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        print(f'    "{snippet}"')
        print(f"    → {s.message}")
        if s.replacement is not None and s.replacement != "":
            print(f"    fix: '{s.replacement}'")
        if explain:
            why = " ".join(REGISTRY[s.rule_id].why.split())
            print(_c(DIM, f"    why: {why}"))

    if metrics:
        d = metrics.to_dict()
        print(f"\n  {_c(BOLD, 'metrics')} — {d['sentences']} sentences, "
              f"{d['words']} words, mean sentence {d['mean_sentence_len']} "
              f"words ({d['long_sentences']} over 40)")
        print(f"    nominalizations /100w: {d['nominalizations_per_100w']}"
              f"   hedges /100w: {d['hedges_per_100w']}"
              f"   boosters /100w: {d['boosters_per_100w']}")
        print(f"    calibration: {d['hedge_booster_balance']}   "
              f"self-mention /100w: {d['self_mention_per_100w']}")
        if d["passive_share_by_section"]:
            shares = "  ".join(f"{k}: {int(v * 100)}%"
                               for k, v in d["passive_share_by_section"].items())
            print(f"    passive sentences by section: {shares}")
        print(_c(DIM, "    (a read-out, not a score — Methods is allowed "
                      "its passives)"))
    print()


def cmd_rules(_args) -> int:
    from . import (rules_lexical, rules_syntax,  # noqa: F401 (register)
                   rules_spelling, rules_grammar)
    by_cat: dict[Category, list] = {}
    for r in REGISTRY.values():
        by_cat.setdefault(r.category, []).append(r)
    for cat in (Category.CORRECTION, Category.IMPROVEMENT,
                Category.CONVENTION, Category.PREFERENCE):
        rules = sorted(by_cat.get(cat, []), key=lambda r: r.id)
        if not rules:
            continue
        print(f"\n{_c(COLORS[cat], cat.value.upper())}")
        for r in rules:
            scope = ""
            if r.sections_only:
                scope = f"  (only: {', '.join(sorted(r.sections_only))})"
            elif r.sections_excluded:
                scope = f"  (not in: {', '.join(sorted(r.sections_excluded))})"
            print(f"  {r.id}  {r.name:<24} {r.short}{_c(DIM, scope)}")
    print(f"\n{_c(DIM, 'researchly explain <ID> for the full rationale.')}\n")
    return 0


def cmd_polish(args) -> int:
    """Deterministic rule-composed rewrite of a passage (no LLM)."""
    from .transform import polish
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        kind = ("markdown" if Path(args.file).suffix.lower()
                in {".md", ".qmd", ".rmd"} else "plain")
    else:
        text = args.text or sys.stdin.read()
        kind = args.kind
    result = polish(text, get_nlp(), kind=kind)
    if not result.changed:
        print("\nNothing to safely rewrite — no composable edits found.\n")
        return 0
    print()
    color = _use_color()
    for seg in result.segments:
        if seg["op"] == "del":
            print(_c("\033[31m", seg["text"]) if color
                  else "[-" + seg["text"] + "-]", end="")
        elif seg["op"] == "ins":
            print(_c("\033[32m", seg["text"]) if color
                  else "{+" + seg["text"] + "+}", end="")
        else:
            print(seg["text"], end="")
    print("\n")
    for e in result.edits:
        print(f"  {e['rule_id']} {e['rule_name']}: "
              f"'{e['before']}' -> '{e['after']}'")
    if result.notes:
        print(_c(DIM, f"\n  + {len(result.notes)} judgement-call flags left "
                      "alone (run `check` to see them)"))
    print()
    return 0


def cmd_review(args) -> int:
    """Critical-reader review lens (Wallace & Wray five questions)."""
    from .review import build_review, render_review
    if args.file:
        p = Path(args.file)
        text = p.read_text(encoding="utf-8")
        kind = ("markdown" if p.suffix.lower() in {".md", ".qmd", ".rmd"}
                else "latex" if p.suffix.lower() in {".tex", ".ltx"}
                else "plain")
    else:
        text = args.text or sys.stdin.read()
        kind = "plain"
    if len(text.strip()) < 200:
        print("\nGive me a document (FILE argument, --file, or stdin).\n")
        return 2
    print("\n" + render_review(build_review(text, get_nlp(), kind)) + "\n")
    return 0


def cmd_narrative(args) -> int:
    """The narrative map: moves per section, missing links, hedging."""
    from .discourse.narrative import render_narrative
    from .api import analyze, get_nlp
    if args.file:
        p = Path(args.file)
        text = p.read_text(encoding="utf-8")
        kind = ("markdown" if p.suffix.lower() in {".md", ".qmd", ".rmd"}
                else "latex" if p.suffix.lower() in {".tex", ".ltx"}
                else "plain")
    else:
        text = args.text or sys.stdin.read()
        kind = "plain"
    if len(text.strip()) < 200:
        print("\nGive me a document (FILE argument, --file, or stdin).\n")
        return 2
    a = analyze(text, kind=kind, nlp=get_nlp(), with_narrative=True,
                with_metrics=False)
    print("\n" + render_narrative(a.narrative) + "\n")
    return 0


def cmd_abstract(args) -> int:
    """Six-part abstract completeness lens (Belcher/Pallas)."""
    from .discourse.abstract_lens import FRAMES, MOVES, analyze
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = args.text or sys.stdin.read()
    text = text.strip()
    if len(text) < 100:
        print("\nGive me the abstract text (argument, --file, or stdin).\n")
        return 2

    result = analyze(text)
    print(f"\n{_c(BOLD, 'Abstract lens — six-part completeness')} "
          f"{_c(DIM, '(Belcher 2021 / Pallas 2022)')}\n")
    missing = []
    for move in MOVES:
        r = result[move]
        mark = _c("\033[32m", "present") if r["present"] else \
            _c("\033[31m", "MISSING")
        print(f"  {move:<13} {mark}")
        if r["present"] and r["evidence"]:
            print(_c(DIM, f'      "{r["evidence"]}"'))
        if not r["present"]:
            missing.append(move)
    if missing:
        print(f"\n  {_c(BOLD, 'Frames for the missing moves')} "
              f"{_c(DIM, '(fill in the brackets)')}")
        for move in missing:
            print(f"    {move}: {FRAMES[move]}")
    else:
        green = "\033[32m"                     # no backslashes in f-string
        ok = _c(green, "All six moves detected.")
        note = _c(DIM, "Signal-based check — read it once more as the "
                       "sceptical reviewer.")
        print(f"\n  {ok} {note}")
    words = len(text.split())
    print(_c(DIM, f"\n  length: {words} words — match the call for papers; "
                  "200-300 is typical, and don't come in far under a high "
                  "limit.\n"))
    return 0


def cmd_dict(args) -> int:
    """Personal dictionary for the spelling layer (S001)."""
    from . import spelling
    if args.action == "add":
        if not args.words:
            print("usage: researchly dict add <word> [<word>...]")
            return 2
        for w in args.words:
            ok = spelling.add_to_user_dictionary(w)
            print(f"  {'added' if ok else 'FAILED'}: {w.lower()}")
        return 0
    words = sorted(spelling.user_dictionary())
    if not words:
        print("\nYour dictionary is empty. Add your terminology with:\n"
              "  researchly dict add seroprevalence\n")
    else:
        print(f"\nYour dictionary ({len(words)} words, stored in "
              f"{spelling.USER_DICT_FILE}):\n  " + ", ".join(words) + "\n")
    return 0


def cmd_stats(_args) -> int:
    """Which rules earn their keep on YOUR writing (local telemetry)."""
    from . import telemetry
    report = telemetry.summarize()
    if not report:
        print("\nNo usage data yet. Telemetry is collected locally (only on "
              "this computer,\nin ~/.researchly/telemetry.jsonl) when you "
              "use the Word add-in.\n")
        return 0
    print(f"\n{_c(BOLD, 'Researchly usage — per-rule keep rates')}"
          f"  {_c(DIM, '(local data only)')}\n")
    print(f"  {'rule':<7}{'shown':>6}{'goto':>6}{'apply':>6}{'dism.':>7}"
          f"{'muted':>7}{'keep':>6}  verdict")
    for rule, c in report.items():
        print(f"  {rule:<7}{c['shown']:>6}{c['goto']:>6}{c['applied']:>6}"
              f"{c['dismissed']:>7}{c['muted']:>7}{c['keep_rate']:>6}"
              f"  {_c(DIM, c['verdict'])}")
    note = ("keep = (shown - dismissed - muted) / shown. Rules with low "
            "keep rates are candidates to attenuate or mute - that "
            "decision stays yours.")
    print("\n" + _c(DIM, note) + "\n")
    return 0


def cmd_explain(args) -> int:
    from . import (rules_lexical, rules_syntax,  # noqa: F401 (register)
                   rules_spelling, rules_grammar)
    r = REGISTRY.get(args.rule_id.upper())
    if not r:
        print(f"researchly: unknown rule: {args.rule_id}", file=sys.stderr)
        return 2
    print(f"\n{BOLD if _use_color() else ''}{r.id} — {r.name}{RESET if _use_color() else ''}"
          f"  [{r.category.value}]"
          + (f"  (guide {r.source})" if r.source else ""))
    print(f"\n{r.short}\n")
    print(" ".join(r.why.split()))
    print()
    return 0


# --- entry -----------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="researchly",
        description="Research-focused writing checker (v0.1 prototype).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="check one or more files")
    p_check.add_argument("files", nargs="+")
    p_check.add_argument("--all", action="store_true",
                         help="include Preference suggestions")
    p_check.add_argument("--explain", action="store_true",
                         help="print the full rationale for each suggestion")
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--disable", default="",
                         help="comma-separated rule ids to mute")
    p_check.add_argument("--no-metrics", action="store_true")
    p_check.add_argument("--mode", choices=config_mod.MODES, default=None,
                         help="draft: sentence-level checks only; revise: "
                              "everything (default: your settings)")
    p_check.set_defaults(func=cmd_check)

    p_rules = sub.add_parser("rules", help="list all rules")
    p_rules.set_defaults(func=cmd_rules)

    p_explain = sub.add_parser("explain", help="explain one rule in full")
    p_explain.add_argument("rule_id")
    p_explain.set_defaults(func=cmd_explain)

    p_stats = sub.add_parser(
        "stats", help="per-rule keep rates from your local usage data")
    p_stats.set_defaults(func=cmd_stats)

    p_rev = sub.add_parser(
        "review",
        help="critical-reader review lens (Wallace & Wray five questions)")
    p_rev.add_argument("text", nargs="?", default=None)
    p_rev.add_argument("--file", default=None)
    p_rev.set_defaults(func=cmd_review)

    p_nar = sub.add_parser(
        "narrative",
        help="narrative map: moves per section, missing links, hedging")
    p_nar.add_argument("text", nargs="?", default=None)
    p_nar.add_argument("--file", default=None)
    p_nar.set_defaults(func=cmd_narrative)

    p_abs = sub.add_parser(
        "abstract",
        help="six-part abstract completeness lens (Belcher/Pallas)")
    p_abs.add_argument("text", nargs="?", default=None)
    p_abs.add_argument("--file", default=None)
    p_abs.set_defaults(func=cmd_abstract)

    p_dict = sub.add_parser(
        "dict", help="personal spelling dictionary (list / add words)")
    p_dict.add_argument("action", nargs="?", default="list",
                        choices=["list", "add"])
    p_dict.add_argument("words", nargs="*")
    p_dict.set_defaults(func=cmd_dict)

    p_polish = sub.add_parser(
        "polish", help="rule-composed rewrite of a passage (no LLM)")
    p_polish.add_argument("text", nargs="?", default=None,
                          help="text to polish (or use --file / stdin)")
    p_polish.add_argument("--file", default=None)
    p_polish.add_argument("--kind", default="plain",
                          choices=["plain", "markdown", "latex"])
    p_polish.set_defaults(func=cmd_polish)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
