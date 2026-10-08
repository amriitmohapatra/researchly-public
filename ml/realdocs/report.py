"""Summarise a run: report.json (aggregate) and report.md (for people).

    python ml/realdocs/report.py [--out DIR]

Reads results.jsonl and run_meta.json from --out (written by run.py) and
writes report.json and report.md beside them. Neither contains document
text: only ids, rule ids, error codes, counts, offsets and timings.
Snippets stay in samples.jsonl, which this script never reads.

Exit status (the CI gate): 1 if any invariant failed; anything crashed or
timed out; a reader touched the network, another file or a process; a file
was refused that should parse (no `expect`, or `expect: parse`); a file
marked `expect: error` was read anyway; the grammar tier was required but
not running; a JATS article could not be converted or a cached file was
missing; or nothing was checked at all. Skipped downloads (Europe PMC
404s, preprint-server 403s) and a LaTeX project whose detected main file
differs from the manifest's `main:` are reported, not failed. Flags per
1000 words are reported, not gated (yet).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

RAN = ("ok", "invariant_failure")
# Item states that mean the bench itself could not do its job on a document
# it had in hand (a converter bug, a damaged cache). Download and unpacking
# problems (network errors, 404s, 403s, a server sending junk) are reported.
BENCH_BROKEN = ("convert_error", "cache_error")
WORD_RATIO_BAND = (0.85, 1.15)
TOP = 15


S2B_RULES = ("X1", "X2", "X3", "X4", "F612", "F613", "N101", "N102", "W211")


def _rate(flags: int, words: int) -> float:
    return round(1000 * flags / words, 2) if words else 0.0


def _format_key(rec: dict) -> str:
    if rec["rendering"] == "native":
        return rec["format"]
    return f"{rec['format']}/{rec['rendering']}"


def build(records: list[dict], meta: dict) -> dict:
    docs = [r for r in records if r["type"] == "doc"]
    items = [r for r in records if r["type"] == "item"]
    parities = [r for r in records if r["type"] == "parity"]
    ran = [r for r in docs if r["status"] in RAN]

    failures: list[dict] = []
    warnings: list[dict] = []
    crashes: Counter = Counter()
    invariants: dict[str, dict] = {}
    unexpected: Counter = Counter()
    expected: Counter = Counter()
    for r in docs:
        where = {"id": r["id"], "rendering": r["rendering"]}
        if r["status"] in ("crash", "timeout"):
            key = f"{r['stage']}:{r['error_type']}"
            crashes[key] += 1
            failures.append({"kind": r["status"], **where, "detail": key})
        elif r["status"] == "ingest_error":
            unexpected[r["error_code"]] += 1
            failures.append({"kind": "ingest_error", **where,
                             "detail": r["error_code"]})
        elif r["status"] == "expected_error":
            expected[r["error_code"]] += 1
        elif r["status"] == "main_undetermined":
            warnings.append({"kind": "main_undetermined", **where,
                             "detail": "the zip adapter could not choose a "
                                       "main .tex (manifest: "
                                       f"{r.get('main_expected')})"})
        elif r["status"] == "refused_too_large":
            warnings.append({"kind": "refused_too_large", **where,
                             "detail": "over the engine's size limit"})
        for check, f in (r.get("invariant_failures") or {}).items():
            inv = invariants.setdefault(check, {"documents": 0, "count": 0})
            inv["documents"] += 1
            inv["count"] += f["count"]
            failures.append({"kind": "invariant", **where,
                             "detail": f"{check} x{f['count']}"})
        if r.get("io_during_read"):
            failures.append({"kind": "io_during_read", **where,
                             "detail": ", ".join(r["io_during_read"])})
        if r.get("expectation_unmet"):
            failures.append({"kind": "expectation_unmet", **where,
                             "detail": "expected an IngestError, but the "
                                       "file was read"})
        if r.get("main_match") is False:
            warnings.append({"kind": "main_file_mismatch", **where,
                             "detail": f"picked {r['main_picked']}, manifest "
                                       f"says {r['main_expected']}"})
        ratio = r.get("word_ratio")
        if ratio is not None and not (WORD_RATIO_BAND[0] <= ratio
                                      <= WORD_RATIO_BAND[1]):
            warnings.append({"kind": "word_count_drift", **where,
                             "detail": f"prose words {ratio:.2f}x expected"})

    item_states = Counter(r["status"] for r in items)
    for r in items:
        if r["status"] in BENCH_BROKEN:
            failures.append({"kind": r["status"], "id": r["id"],
                             "rendering": "", "detail": r.get("error") or ""})
        elif not r["status"].startswith("skipped_"):
            warnings.append({"kind": r["status"], "id": r["id"],
                             "rendering": "", "detail": r.get("error") or ""})

    if meta.get("require_grammar") and meta.get("grammar") != "running":
        failures.append({"kind": "grammar_tier", "id": "", "rendering": "",
                         "detail": "the grammar tier was required but is "
                                   "not running (Java or LanguageTool?)"})
    if not ran and not expected:
        failures.append({"kind": "nothing_checked", "id": "", "rendering": "",
                         "detail": "no document was read and analysed"})

    def rates(key) -> dict:
        words, flags = Counter(), Counter()
        for r in ran:
            words[key(r)] += r["prose_words"]
            flags[key(r)] += r["flags"]
        return {k: {"documents": sum(1 for r in ran if key(r) == k),
                    "words": words[k], "flags": flags[k],
                    "per_1000": _rate(flags[k], words[k])}
                for k in sorted(words)}

    by_rule: Counter = Counter()
    rule_docs: Counter = Counter()
    by_tier: Counter = Counter()
    for r in ran:
        by_rule.update(r["by_rule"])
        rule_docs.update(r["by_rule"].keys())
        by_tier.update(r["by_tier"])

    div: dict[tuple, dict] = {}
    for p in parities:
        for d in p["divergent"]:
            a, b = d["pair"].split("/")
            k = (d["pair"], d["rule"])
            e = div.setdefault(k, {"pair": d["pair"], "rule": d["rule"],
                                   "items": 0, a: 0, b: 0})
            e["items"] += 1
            e[a] += d[a]
            e[b] += d[b]
    divergences = sorted(div.values(), key=lambda e: (
        -e["items"], -abs(sum(v for k, v in e.items()
                              if k not in ("pair", "rule", "items")))))

    # The S2b structure and consistency rules by rendering: published
    # articles cite every figure in order, so their flags here are mostly
    # false positives (P32).
    s2b: dict = {}
    for r in ran:
        for rule, n in r["by_rule"].items():
            if rule.startswith(S2B_RULES):
                cell = s2b.setdefault(rule, Counter())
                cell[_format_key(r)] += n

    slowest = sorted(ran, key=lambda r: -(r["parse_s"] + r["analyze_s"]))
    total_words = sum(r["prose_words"] for r in ran)
    total_flags = sum(r["flags"] for r in ran)
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": meta.get("manifest"),
        "gate": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "totals": {
            "items": meta.get("items"),
            "items_not_run": dict(item_states),
            "files": len(docs),
            "analysed": len(ran),
            "expected_errors": dict(expected),
            "words": total_words,
            "flags": total_flags,
            "seconds": meta.get("seconds"),
        },
        "grammar": meta.get("grammar"),
        "health": [{k: t.get(k) for k in ("tier", "state", "ok")}
                   for t in meta.get("health", [])],
        "invariants": invariants,
        "crashes": dict(crashes),
        "unexpected_ingest_errors": dict(unexpected),
        "flags_per_1000": {
            "overall": _rate(total_flags, total_words),
            "by_discipline": rates(lambda r: r["discipline"]),
            "by_format": rates(_format_key),
        },
        "top_rules": [{"rule": k, "count": v, "documents": rule_docs[k]}
                      for k, v in by_rule.most_common(TOP)],
        "by_tier": dict(by_tier.most_common()),
        "s2b_by_format": {k: dict(sorted(v.items()))
                          for k, v in sorted(s2b.items())},
        "parity": {"items": len(parities),
                   "tolerance": meta.get("parity_tolerance"),
                   "set_aside": _set_aside(parities),
                   "divergences": divergences[:TOP * 2]},
        "sections": _sections(ran),
        "slowest": [{"id": r["id"], "rendering": r["rendering"],
                     "seconds": round(r["parse_s"] + r["analyze_s"], 2),
                     "parse_s": r["parse_s"], "words": r["prose_words"],
                     "chars": r["chars"]} for r in slowest[:10]],
    }


def _set_aside(parities: list[dict]) -> dict:
    out: dict[str, Counter] = defaultdict(Counter)
    for p in parities:
        for name, c in p["set_aside"].items():
            out[name].update(c)
    return {k: dict(v) for k, v in sorted(out.items())}


def _sections(ran: list[dict]) -> dict:
    """How often each rendering found any IMRaD section at all."""
    out: dict[str, dict] = {}
    for r in ran:
        e = out.setdefault(_format_key(r), {"documents": 0, "with_sections": 0,
                                            "headings": 0})
        e["documents"] += 1
        e["with_sections"] += 1 if r["sections"] else 0
        e["headings"] += r["headings"]
    return out


def _table(rows: list[list], head: list[str]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines + [""]


def markdown(rep: dict) -> str:
    t = rep["totals"]
    out = [f"# Real-document bench: **{rep['gate'].upper()}**", "",
           f"Manifest `{rep['manifest']}`; {t['items']} item(s), "
           f"{t['files']} file(s) read, {t['analysed']} analysed, "
           f"{t['words']:,} prose words, {t['flags']:,} flags "
           f"({rep['flags_per_1000']['overall']}/1000w, preferences "
           f"excluded), {t['seconds']} s. Grammar tier: {rep['grammar']}.",
           ""]
    if t["items_not_run"]:
        out += ["Items not run: " + ", ".join(
            f"{k} {v}" for k, v in sorted(t["items_not_run"].items())), ""]
    if t["expected_errors"]:
        out += ["Refused as expected (manifest `expect:`): " + ", ".join(
            f"{k} {v}" for k, v in sorted(t["expected_errors"].items())), ""]

    out += ["## Failures", ""]
    if rep["failures"]:
        out += _table([[f["kind"], f["id"], f["rendering"], f["detail"]]
                       for f in rep["failures"]],
                      ["kind", "item", "rendering", "detail"])
    else:
        out += ["None: every invariant held and nothing crashed.", ""]
    if rep["crashes"]:
        out += ["Crashes by type: " + ", ".join(
            f"`{k}` {v}" for k, v in rep["crashes"].items()), ""]
    if rep["invariants"]:
        out += _table([[k, v["documents"], v["count"]]
                       for k, v in sorted(rep["invariants"].items())],
                      ["invariant", "documents", "violations"])

    out += ["## Flags per 1000 prose words", ""]
    for title, key in (("By format", "by_format"),
                       ("By discipline", "by_discipline")):
        rows = [[k, v["documents"], f"{v['words']:,}", v["flags"],
                 v["per_1000"]]
                for k, v in rep["flags_per_1000"][key].items()]
        if rows:
            out += [f"**{title}**", ""]
            out += _table(rows, [key.split("_")[1], "files", "words", "flags",
                                 "per 1000w"])

    if rep["top_rules"]:
        out += ["## Top rules", ""]
        out += _table([[r["rule"], r["count"], r["documents"]]
                       for r in rep["top_rules"]],
                      ["rule", "flags", "files"])

    s2b = rep.get("s2b_by_format") or {}
    if s2b:
        fmts = sorted({f for v in s2b.values() for f in v})
        out += ["## Structure and consistency checks (S2b) by format", ""]
        out += _table([[rule] + [v.get(f, 0) for f in fmts]
                       for rule, v in s2b.items()], ["rule"] + fmts)

    par = rep["parity"]
    if par["items"]:
        out += ["## Format parity (JATS items)", "",
                f"{par['items']} article(s) rendered as plain, docx and tex. "
                "Set aside before comparing (citations and maths are masked "
                "only in LaTeX; Word table cells are text only in Word): "
                + "; ".join(f"{k}: {v.get('near_marker', 0)} near a "
                            f"citation or maths, {v.get('in_table', 0)} "
                            "in a table" for k, v in par["set_aside"].items())
                + ".", ""]
        if par["divergences"]:
            rows = []
            for d in par["divergences"][:TOP]:
                a, b = d["pair"].split("/")
                rows.append([d["pair"], d["rule"], d["items"], d[a], d[b]])
            out += _table(rows, ["pair", "rule", "articles", "first count",
                                 "second count"])
            out += ["Example spans are in `samples.jsonl` in the run "
                    "artifact.", ""]
        else:
            out += ["No rule diverged beyond tolerance.", ""]

    if rep["sections"]:
        out += ["## Sections found", ""]
        out += _table([[k, v["documents"], v["with_sections"], v["headings"]]
                       for k, v in sorted(rep["sections"].items())],
                      ["format", "files", "with IMRaD sections",
                       "headings"])

    if rep["slowest"]:
        out += ["## Slowest files", ""]
        out += _table([[s["id"], s["rendering"], s["seconds"], s["parse_s"],
                        f"{s['words']:,}"] for s in rep["slowest"]],
                      ["item", "rendering", "total s", "read s", "words"])

    if rep["warnings"]:
        out += ["## Warnings (not failures)", ""]
        out += _table([[w["kind"], w["id"], w["rendering"], w["detail"]]
                       for w in rep["warnings"][:40]],
                      ["kind", "item", "rendering", "detail"])
        if len(rep["warnings"]) > 40:
            out += [f"... and {len(rep['warnings']) - 40} more in "
                    "report.json.", ""]
    if rep["health"]:
        out += ["Engine tiers: " + ", ".join(
            f"{h['tier']} {h['state']}" for h in rep["health"]), ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    out = common.outside_repo(args.out or common.default_out())
    results = out / "results.jsonl"
    if not results.exists():
        sys.exit(f"no {results}; run run.py first")
    records = [json.loads(line) for line in
               results.read_text(encoding="utf-8").splitlines() if line]
    meta = json.loads((out / "run_meta.json").read_text())
    rep = build(records, meta)
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    md = markdown(rep)
    (out / "report.md").write_text(md + "\n")
    print(md)
    return 1 if rep["gate"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
