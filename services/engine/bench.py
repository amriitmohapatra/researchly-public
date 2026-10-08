"""Latency benchmark for ARCHITECTURE.md Q1/Q2 (warm p50/p95).

    # against a running service (container, compose, staging):
    python bench.py --url http://localhost:8080
    # in-process (no HTTP; the engine alone), with the same text:
    python bench.py --in-process

Two workloads, both SYNTHETIC — generated here from a fixed seed, never
taken from the thesis corpus (ml/dogfood/text, Sample_thesis_drafts):

- Q1 "paragraph": ~300 words, target p95 ≤ 800 ms warm;
- Q2 "chapter":   ~10,000 words with IMRaD headings, target p95 ≤ 6 s warm.

Each workload is sent `--warmup` times first (not timed), then timed
`--n-paragraph` / `--n-chapter` times. Client-side wall time is reported
(includes HTTP and JSON for --url), plus the server's own `elapsed_ms`.

Caveat printed with the results: numbers depend on the machine. A laptop or
CI sandbox is not a Cloud Run instance (1 vCPU engine container + sidecar);
the staging measurement is the one that ticks Q1/Q2 in PLAN.md.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
import urllib.request

SUBJECTS = ["The model", "Transmission", "The reproduction number",
            "Weekly incidence", "The posterior distribution",
            "Vaccine coverage", "The surveillance system", "Case ascertainment",
            "The serial interval", "Hospital admissions", "The cohort",
            "Seroprevalence", "The intervention", "Mobility",
            "The renewal equation", "Reporting delay"]
VERBS = ["was estimated from", "increased with", "declined after",
         "was calibrated against", "was associated with", "varied across",
         "was fitted to", "depended on", "was sensitive to",
         "was consistent with", "was robust to", "was compared with"]
OBJECTS = ["the line-list data", "district-level case counts",
           "the age-structured contact matrix", "the prior predictive check",
           "weekly mortality reports", "the climate covariates",
           "the hierarchical random effects", "the observation model",
           "the negative binomial likelihood", "the sensitivity analysis",
           "the counterfactual scenario", "laboratory-confirmed infections"]
TAILS = ["in every region", "during the second wave", "over the study period",
         "after adjustment for reporting delays", "with wide credible intervals",
         "in the urban districts", "under the baseline scenario", "",
         "although the evidence was limited", "which may suggest a seasonal effect",
         "as shown in Table 2", "by the study team"]
HEADINGS = ["Introduction", "Methods", "Results", "Discussion"]


def sentence(rng: random.Random) -> str:
    s = " ".join(x for x in (rng.choice(SUBJECTS), rng.choice(VERBS),
                             rng.choice(OBJECTS), rng.choice(TAILS)) if x)
    if rng.random() < 0.06:
        s = s.replace(" was ", " were ", 1)            # an agreement slip
    if rng.random() < 0.04:
        s = s.replace("the ", "teh ", 1)               # a typo
    if rng.random() < 0.05:
        s = "It is very clear that " + s[0].lower() + s[1:]
    return s + "."


def paragraph(rng: random.Random, words: int) -> str:
    out, n = [], 0
    while n < words:
        s = sentence(rng)
        out.append(s)
        n += len(s.split())
    return " ".join(out)


def make_paragraph(seed: int = 7) -> str:
    return paragraph(random.Random(seed), 300)


def make_chapter(seed: int = 11, words: int = 10_000) -> str:
    rng = random.Random(seed)
    parts, n = [], 0
    per_section = words // len(HEADINGS)
    for h in HEADINGS:
        parts.append(h)
        got = 0
        while got < per_section:
            p = paragraph(rng, rng.randint(90, 160))
            parts.append(p)
            got += len(p.split())
        n += got
    return "\n\n".join(parts) + "\n"


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def http_runner(url: str):
    endpoint = url.rstrip("/") + "/v1/analyze"

    def run(text: str):
        data = json.dumps({"format": "plain", "content": text}).encode()
        req = urllib.request.Request(
            endpoint, data=data, method="POST",
            headers={"content-type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
        wall = (time.perf_counter() - t0) * 1000
        grammar = next((t["ok"] for t in body["health"]
                        if t["tier"] == "grammar"), False)
        return wall, body["elapsed_ms"], len(body["suggestions"]), grammar
    return run


def inprocess_runner():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    from researchly_service import engine_adapter
    from researchly_service.schemas import AnalyzeOptions
    engine_adapter.warm_up()

    def run(text: str):
        t0 = time.perf_counter()
        resp = engine_adapter.run_analysis(text, "plain", AnalyzeOptions())
        wall = (time.perf_counter() - t0) * 1000
        grammar = next((t.ok for t in resp.health if t.tier == "grammar"),
                       False)
        return wall, resp.elapsed_ms, len(resp.suggestions), grammar
    return run


def measure(run, text, n, warmup):
    if n == 0:                       # --n-chapter 0: skip this size entirely
        return {"n": 0}
    for _ in range(warmup):
        run(text)
    walls, servers, sugg, gram = [], [], 0, True
    for _ in range(n):
        w, s, k, g = run(text)
        walls.append(w)
        servers.append(s)
        sugg, gram = k, gram and g
    return {"n": n, "p50_ms": round(pct(walls, 0.5)),
            "p95_ms": round(pct(walls, 0.95)),
            "max_ms": round(max(walls)),
            "server_p50_ms": round(statistics.median(servers)),
            "suggestions": sugg, "grammar_ok": gram}


def _count(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url")
    g.add_argument("--in-process", action="store_true")
    ap.add_argument("--n-paragraph", type=_count, default=40,
                    help="timed paragraph runs; 0 skips the paragraph")
    ap.add_argument("--n-chapter", type=_count, default=10,
                    help="timed chapter runs; 0 skips the chapter")
    ap.add_argument("--warmup", type=_count, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    run = http_runner(a.url) if a.url else inprocess_runner()
    para, chap = make_paragraph(), make_chapter()
    res = {
        "target": a.url or "in-process",
        "machine": f"{platform.machine()} {platform.system()} "
                   f"{os.cpu_count()} CPUs, Python {platform.python_version()}",
        "paragraph": dict(words=len(para.split()),
                          **measure(run, para, a.n_paragraph, a.warmup)),
        "chapter": dict(words=len(chap.split()),
                        **measure(run, chap, a.n_chapter, a.warmup)),
    }
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"target: {res['target']}  ({res['machine']})")
    for name, q, limit in (("paragraph", "Q1", 800), ("chapter", "Q2", 6000)):
        r = res[name]
        if not r["n"]:
            print(f"{q} {name:9s} skipped (n=0)")
            continue
        verdict = "within" if r["p95_ms"] <= limit else "OVER"
        print(f"{q} {name:9s} {r['words']:>6} words  n={r['n']:<3} "
              f"p50 {r['p50_ms']:>6} ms  p95 {r['p95_ms']:>6} ms  "
              f"max {r['max_ms']:>6} ms  server p50 {r['server_p50_ms']} ms  "
              f"[{verdict} {limit} ms]  suggestions={r['suggestions']} "
              f"grammar_ok={r['grammar_ok']}")
    if not a.url:
        print("caveat: measured on this machine, not on a Cloud Run instance; "
              "staging numbers are the ones that tick Q1/Q2.")
    else:
        print("note: p50/p95 include the network from here; server p50 is "
              "the engine's own time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
