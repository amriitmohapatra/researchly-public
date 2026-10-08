"""Run every fetched document through every file reader and the engine.

    python ml/realdocs/run.py [--cache DIR] [--out DIR] [--require-grammar]

For each item fetched by fetch.py: a JATS article becomes three renderings
(plain .txt, .docx, .tex; see convert.py); any other item is checked as the
file(s) it is. Each file goes through `ingest.load_bytes(name, data)` and
`api.analyze(doc, show_preferences=True)` (spaCy loaded once; the grammar
tier on when available), and the result is checked against invariants that
must hold for EVERY document:

- `masked_length`    len(doc.masked) == len(doc.original);
- `segments`         segments cover the text in order, and each one's text
                     equals its slice of the source file (for an Overleaf
                     zip, of the member's text);
- `readback`         a .docx built by convert.py reads back as exactly the
                     paragraphs written into it;
- `span_bounds`      every suggestion has 0 <= start <= end <= len(original);
- `span_text`        original[start:end] == suggestion.text;
- `span_in_masked`   no suggestion starts or ends inside masked material
                     (maths, citations, code: `Document.masked_content`);
- nothing crashes (an exception other than IngestError), and nothing hangs:
  each file runs in a forked worker with a time limit per stage
  (--read-timeout, default 60 s; --analyze-timeout, default 900 s);
- reading touches nothing but the bytes given: an audit hook records any
  file opened outside Python's own code, socket or process use while
  `load_bytes` runs (`io_during_read`; the XXE probe relies on it).

The manifest's `expect` says what reading should do: `parse` (or absent):
an IngestError is a failure; `error`: an IngestError is the pass and a read
is a failure; `either`: both pass. Two refusals are findings, not failures:
a real manuscript over the engine's size limit, and a LaTeX project whose
main file the zip adapter cannot choose. For LaTeX projects the detected
main file is compared with the manifest's `main:` note.

For JATS items, per-rule counts are compared across the three renderings
(format parity). Findings in Word table cells, and findings touching a
citation or maths span (which only LaTeX masks), are set aside first, so a
divergence that remains points at a reader. Up to 3 example spans per
divergent rule go to samples.jsonl.

Outputs in --out: results.jsonl and run_meta.json (no document text), and
samples.jsonl (short snippets, ONLY for items whose licence allows it;
see common.snippets_allowed). The console shows ids and counts only.
report.py turns these into report.json / report.md and the exit status.
"""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import posixpath
import sys
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

common.add_core_to_path()

SNIPPET_CHARS = 120
EXAMPLES_PER_CHECK = 3
SAMPLES_PER_RULE = 3
PARITY_PAIRS = (("docx", "tex"), ("plain", "docx"), ("plain", "tex"))
NEAR_MARKER = 2        # characters of slack around a citation or maths span


# -- invariants ---------------------------------------------------------------

def source_texts(filename: str, data: bytes) -> dict[str, str] | None:
    """What each segment path should slice back to, or None when the reader
    does not keep a source mapping (.docx text is derived, not sliced)."""
    from researchly.ingest import TEXT_SUFFIXES, suffix_of
    suffix = suffix_of(filename)
    if suffix == ".zip":
        out = {}
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".tex"):
                    continue
                name = posixpath.normpath(info.filename.replace("\\", "/"))
                try:
                    out[name] = zf.read(info).decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
        return out
    if suffix in TEXT_SUFFIXES:
        return {filename: data.decode("utf-8-sig")}
    return None


def check_invariants(doc, suggestions, sources: dict | None,
                     expect_text: str | None = None) -> dict:
    """{check: {"count": n, "examples": [{start, end, rule}]}}; empty when
    every invariant holds. Examples carry offsets, never text."""
    fails: dict[str, dict] = {}

    def fail(check: str, **example) -> None:
        f = fails.setdefault(check, {"count": 0, "examples": []})
        f["count"] += 1
        if len(f["examples"]) < EXAMPLES_PER_CHECK:
            f["examples"].append(example)

    original, masked = doc.original, doc.masked
    n = len(original)
    if len(masked) != n:
        fail("masked_length", original=n, masked=len(masked))

    if not doc.segments:
        fail("segments", reason="no segments")
    pos = 0
    for seg in sorted(doc.segments, key=lambda s: s.start):
        if seg.start != pos or seg.end < seg.start:
            fail("segments", reason="gap or overlap", start=seg.start,
                 end=seg.end)
        pos = max(pos, seg.end)
        if sources is None:
            continue
        src = sources.get(seg.path)
        if src is None:
            fail("segments", reason="unknown source path", start=seg.start,
                 end=seg.end)
            continue
        want = src[seg.source_start:seg.source_start + seg.end - seg.start]
        if original[seg.start:seg.end] != want:
            fail("segments", reason="text differs from its source slice",
                 start=seg.start, end=seg.end)
    if doc.segments and pos != n:
        fail("segments", reason="segments do not reach the end",
             start=pos, end=n)

    if expect_text is not None and original != expect_text:
        at = next((i for i, (a, b) in enumerate(zip(original, expect_text))
                   if a != b), min(len(original), len(expect_text)))
        fail("readback", start=at, end=at, got_len=n,
             want_len=len(expect_text))

    safe_masked = len(masked) == n
    for s in suggestions:
        ex = {"start": s.start, "end": s.end, "rule": s.rule_id}
        if not (0 <= s.start <= s.end <= n):
            fail("span_bounds", **ex)
            continue
        if original[s.start:s.end] != s.text:
            fail("span_text", **ex)
        if safe_masked and s.end > s.start and (
                doc.masked_content(s.start, s.start + 1)
                or doc.masked_content(s.end - 1, s.end)):
            fail("span_in_masked", **ex)
    return fails


# -- one file -----------------------------------------------------------------

def _snippet(original: str, start: int, end: int) -> str:
    a, b = max(0, start - 40), min(len(original), end + 40)
    return " ".join(original[a:b].split())[:SNIPPET_CHARS]


# Reading a file must touch nothing but the bytes it was given: no network,
# no other files, no processes (TeX is never executed; XML entities are never
# resolved). While a reader runs, an audit hook records any such event.
_WATCH: list | None = None
_HOOKED = False
_ALLOWED: tuple = ()
_IO_EVENTS = ("socket.", "subprocess.Popen", "os.system", "os.exec",
              "os.posix_spawn", "os.spawn", "os.fork", "urllib.Request")


def _audit(event: str, args) -> None:
    if _WATCH is None:
        return
    try:
        if event == "open":
            path = args[0]
            if isinstance(path, int):
                return
            path = os.path.abspath(os.fsdecode(path))
            if not path.startswith(_ALLOWED):
                _WATCH.append("open " + os.path.basename(path))
        elif event.startswith(_IO_EVENTS):
            _WATCH.append(event)
    except Exception:                   # noqa: BLE001 - never break the reader
        _WATCH.append(event)


def install_watch() -> None:
    """Install the audit hook once. Python code and data (the interpreter,
    site-packages, the engine) may be opened; anything else is recorded."""
    global _HOOKED, _ALLOWED
    if _HOOKED:
        return
    import site
    prefixes = {sys.prefix, sys.base_prefix, sys.exec_prefix, str(common.CORE)}
    try:
        prefixes.update(site.getsitepackages())
        prefixes.add(site.getusersitepackages())
    except AttributeError:
        pass
    _ALLOWED = tuple(os.path.abspath(p) + os.sep for p in prefixes)
    sys.addaudithook(_audit)
    _HOOKED = True


@dataclass
class Outcome:
    """What parity and samples need from one analysed file (picklable)."""
    document: object
    suggestions: list
    health: list


def base_record(item: dict, rendering) -> dict:
    return {"type": "doc", "id": item["id"], "rendering": rendering.name,
            "format": item["format"], "source": item["source"],
            "kind": item["kind"], "discipline": item["discipline"],
            "licence": item.get("licence"), "file": rendering.filename,
            "bytes": len(rendering.data),
            "expect": common.expectation(item)}


def _refusal(item: dict, rendering, err) -> str:
    """Status for a refusal of a file that should parse. Two are findings
    rather than failures: a real manuscript over the engine's size limit
    (a product decision), and a LaTeX project whose main file the zip
    adapter cannot choose (the manifest's `main:` says which it is)."""
    if err.code == "payload_too_large" and item["kind"] != "test-file":
        return "refused_too_large"
    if item["format"] == "latex" and rendering.filename.endswith(".zip"):
        from researchly.ingest import IngestError
        from researchly.ingest.latex_project import find_main
        # ingest has no separate code for "no main file", so ask find_main
        # directly. Any other failure to reopen the zip: an ordinary refusal.
        files = {}
        try:
            with zipfile.ZipFile(io.BytesIO(rendering.data)) as zf:
                for info in zf.infolist():
                    name = posixpath.normpath(info.filename.replace("\\", "/"))
                    if name.lower().endswith(".tex"):
                        try:
                            files[name] = zf.read(info).decode("utf-8-sig")
                        except UnicodeDecodeError:
                            files[name] = None
        except (zipfile.BadZipFile, OSError, ValueError, EOFError,
                NotImplementedError, RuntimeError):
            return "ingest_error"
        try:
            find_main(files)
        except IngestError:
            return "main_undetermined"
    return "ingest_error"


def run_file(item: dict, rendering, nlp, cfg, on_read=None):
    """(record, Outcome or None). The record holds no document text.

    `expect` (manifest): None or "parse" -> an IngestError is a failure;
    "error" -> an IngestError is the pass and a clean read is a failure;
    "either" -> both pass. A crash (any other exception) always fails."""
    global _WATCH
    from researchly import api
    from researchly.engine import Category
    from researchly.ingest import IngestError, load_bytes
    from fetch import zip_name

    rec = base_record(item, rendering)
    expect = rec["expect"]
    project = item["format"] == "latex" and rendering.filename.endswith(".zip")
    want = common.notes_of(item).get("main") if project else None
    if want:
        rec["main_expected"] = zip_name(want)
    doc = None
    _WATCH = []
    t0 = time.perf_counter()
    try:
        doc = load_bytes(rendering.filename, rendering.data)
    except IngestError as err:
        rec.update(error_code=err.code,
                   status=("expected_error" if expect in ("error", "either")
                           else _refusal(item, rendering, err)))
    except Exception as err:            # noqa: BLE001 - a crash is the finding
        rec.update(status="crash", stage="read",
                   error_type=type(err).__name__)
    finally:
        seen, _WATCH = _WATCH, None
    rec["parse_s"] = round(time.perf_counter() - t0, 3)
    if seen:
        rec["io_during_read"] = sorted(set(seen))[:10]
    if doc is None:
        return rec, None
    if expect == "error":
        rec["expectation_unmet"] = True
    if project:
        rec["main_picked"] = doc.segments[0].path if doc.segments else None
        if want:
            rec["main_match"] = rec["main_picked"] == rec["main_expected"]
    if on_read is not None:
        on_read()
    t1 = time.perf_counter()
    try:
        analysis = api.analyze(doc, nlp=nlp, cfg=cfg, show_preferences=True)
    except Exception as err:            # noqa: BLE001
        rec.update(status="crash", stage="analyze",
                   error_type=type(err).__name__)
        return rec, None
    rec["analyze_s"] = round(time.perf_counter() - t1, 3)

    sugg = analysis.suggestions
    words = len(doc.masked.split())
    flags = sum(1 for s in sugg if s.category is not Category.PREFERENCE)
    rec.update(
        chars=len(doc.original), prose_words=words,
        expected_words=rendering.expected_words,
        word_ratio=(round(words / rendering.expected_words, 3)
                    if rendering.expected_words else None),
        sections=list(analysis.sections_detected),
        headings=len(doc.headings),
        structure=dict(Counter(s.kind for s in doc.structure)),
        warnings=len(doc.warnings),
        suggestions=len(sugg), flags=flags,
        per_1000=round(1000 * flags / max(words, 1), 2),
        by_rule=dict(Counter(s.rule_id for s in sugg).most_common()),
        by_tier=dict(Counter(s.tier for s in sugg).most_common()),
        by_category=dict(Counter(s.category.value for s in sugg)),
        in_table=sum(1 for s in sugg if doc.in_table(s.start)),
        grammar_ok=analysis.grammar_ok,
    )
    try:
        sources = source_texts(rendering.filename, rendering.data)
    except (zipfile.BadZipFile, UnicodeDecodeError):
        sources = None
    rec["invariant_failures"] = check_invariants(
        doc, sugg, sources, rendering.expect_text)
    rec["status"] = "invariant_failure" if rec["invariant_failures"] else "ok"
    return rec, Outcome(doc, sugg, [t.to_dict() for t in analysis.health])


def _child(conn, item, rendering, cfg) -> None:
    from researchly import api
    try:
        rec, out = run_file(item, rendering, api.get_nlp(), cfg,
                            on_read=lambda: conn.send(("read",)))
        conn.send(("done", rec, out))
    except BaseException as err:        # noqa: BLE001 - report, never hang
        conn.send(("error", type(err).__name__))
    finally:
        conn.close()


def run_isolated(item: dict, rendering, cfg, read_timeout: float,
                 analyze_timeout: float):
    """run_file in a forked worker (spaCy and LanguageTool are already
    loaded, so a fork is cheap) with a time limit on each stage: a reader
    that hangs, or dies outright, becomes a recorded failure instead of a
    stuck job."""
    ctx = multiprocessing.get_context("fork")
    recv, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(send, item, rendering, cfg),
                       daemon=True)
    proc.start()
    send.close()
    stage, msg, limit = "read", None, read_timeout
    try:
        if recv.poll(read_timeout):
            msg = recv.recv()
            if msg[0] == "read":
                stage, limit = "analyze", analyze_timeout
                msg = recv.recv() if recv.poll(analyze_timeout) else None
    except (EOFError, OSError):
        msg = ("died",)
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join()
        recv.close()
    if msg is not None and msg[0] == "done":
        return msg[1], msg[2]
    rec = base_record(item, rendering)
    if msg is None:
        rec.update(status="timeout", stage=stage, error_type="Timeout",
                   limit_s=limit)
    elif msg[0] == "died":
        rec.update(status="crash", stage=stage,
                   error_type=f"WorkerDied(exit {proc.exitcode})")
    else:
        rec.update(status="crash", stage="harness", error_type=msg[1])
    return rec, None


# -- parity -------------------------------------------------------------------

def _near(s, markers) -> bool:
    return any(s.start <= b + NEAR_MARKER and s.end >= a - NEAR_MARKER
               for a, b in markers)


def _kept(analysis, rendering) -> tuple[list, int, int]:
    """Suggestions comparable across formats, plus the two set-aside counts."""
    doc = analysis.document
    markers = rendering.markers
    if rendering.expect_text is not None and doc.original != rendering.expect_text:
        markers = []      # marker offsets are only valid on a clean readback
    kept, in_table, near = [], 0, 0
    for s in analysis.suggestions:
        if doc.in_table(s.start):
            in_table += 1
        elif _near(s, markers):
            near += 1
        else:
            kept.append(s)
    return kept, in_table, near


def _key(s) -> tuple:
    return (s.rule_id, " ".join(s.text.split()).lower())


def parity(item: dict, runs: dict, abs_tol: int, rel_tol: float,
           samples: list | None) -> dict:
    """Per-rule counts across the renderings of one JATS item."""
    kept = {}
    rec = {"type": "parity", "id": item["id"],
           "discipline": item.get("discipline") or "unknown",
           "set_aside": {}, "counts": {}, "divergent": []}
    for name, (rendering, analysis) in runs.items():
        k, in_table, near = _kept(analysis, rendering)
        kept[name] = k
        rec["set_aside"][name] = {"in_table": in_table, "near_marker": near}
        rec["counts"][name] = dict(Counter(s.rule_id for s in k))
    for a, b in PARITY_PAIRS:
        if a not in kept or b not in kept:
            continue
        ca, cb = rec["counts"][a], rec["counts"][b]
        for rule in sorted(set(ca) | set(cb)):
            x, y = ca.get(rule, 0), cb.get(rule, 0)
            if abs(x - y) <= max(abs_tol, rel_tol * max(x, y)):
                continue
            rec["divergent"].append({"pair": f"{a}/{b}", "rule": rule,
                                     a: x, b: y})
            if samples is None:
                continue
            more, less = (a, b) if x > y else (b, a)
            pool = Counter(_key(s) for s in kept[less] if s.rule_id == rule)
            shown = 0
            for s in kept[more]:
                if s.rule_id != rule:
                    continue
                if pool[_key(s)] > 0:
                    pool[_key(s)] -= 1
                    continue
                doc = runs[more][1].document
                samples.append({"type": "parity", "id": item["id"],
                                "pair": f"{a}/{b}", "only_in": more,
                                "rule": rule, "start": s.start, "end": s.end,
                                "snippet": _snippet(doc.original, s.start,
                                                    s.end)})
                shown += 1
                if shown >= EXAMPLES_PER_CHECK:
                    break
    return rec


# -- samples ------------------------------------------------------------------

def collect_samples(item, rec, analysis, samples: list) -> None:
    doc = analysis.document
    per_rule: Counter = Counter()
    for s in analysis.suggestions:
        if per_rule[s.rule_id] >= SAMPLES_PER_RULE:
            continue
        per_rule[s.rule_id] += 1
        samples.append({"type": "suggestion", "id": item["id"],
                        "rendering": rec["rendering"], "rule": s.rule_id,
                        "tier": s.tier, "section": s.section,
                        "start": s.start, "end": s.end,
                        "snippet": _snippet(doc.original, s.start, s.end)})
    for check, f in (rec.get("invariant_failures") or {}).items():
        for ex in f["examples"]:
            a, b = ex.get("start"), ex.get("end")
            if isinstance(a, int) and isinstance(b, int):
                samples.append({"type": "invariant", "id": item["id"],
                                "rendering": rec["rendering"],
                                "check": check, "rule": ex.get("rule"),
                                "start": a, "end": b,
                                "snippet": _snippet(doc.original, a, b)})


# -- driver -------------------------------------------------------------------

def warm_readers() -> None:
    """Read one tiny file of each kind so every reader's imports and
    lazily built tables exist before the I/O watch and the workers start
    (an import opens files; that is not the reader touching the disk)."""
    from researchly.ingest import IngestError, load_bytes
    body = ('<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Warm.</w:t>'
            '</w:r></w:p></w:body></w:document>')
    docx, project = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", body)
        zf.writestr("word/styles.xml", '<w:styles xmlns:w="http://schemas.'
                    'openxmlformats.org/wordprocessingml/2006/main"/>')
    tex = (b"\\documentclass{article}\n\\begin{document}\n"
           b"\\section{Methods}\nWarm $x$ \\cite{a}.\n\\end{document}\n")
    with zipfile.ZipFile(project, "w") as zf:
        zf.writestr("main.tex", tex)
    for name, data in (("w.docx", docx.getvalue()), ("w.tex", tex),
                       ("w.zip", project.getvalue()), ("w.md", b"# Methods\n"),
                       ("w.txt", b"Warm.\n")):
        try:
            load_bytes(name, data)
        except IngestError:
            pass


def files_for(item: dict, entry: dict, cache: Path):
    """[(Rendering)] to check for one fetched item; raises ConvertError."""
    import convert
    folder = cache / common.safe_name(item["id"])
    if item["format"] == "jats":
        return convert.renderings((folder / "article.xml").read_bytes())
    return [convert.Rendering("native", f["name"],
                              (folder / f["name"]).read_bytes())
            for f in entry.get("files", [])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None, help="item ids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-grammar", action="store_true",
                    help="turn the LanguageTool tier off (faster)")
    ap.add_argument("--require-grammar", action="store_true",
                    help="record a failure if the grammar tier is not running")
    ap.add_argument("--no-samples", action="store_true",
                    help="write no snippets at all")
    ap.add_argument("--parity-abs", type=int, default=2,
                    help="counts may differ by this much (default 2)")
    ap.add_argument("--parity-rel", type=float, default=0.25,
                    help="... or by this fraction of the larger (default 0.25)")
    ap.add_argument("--read-timeout", type=float, default=60.0,
                    help="seconds a reader may take on one file (default 60)")
    ap.add_argument("--analyze-timeout", type=float, default=900.0,
                    help="seconds the engine may take on one file "
                         "(default 900)")
    ap.add_argument("--no-isolate", action="store_true",
                    help="run in this process: no time limits (debugging, "
                         "or where fork is unavailable)")
    args = ap.parse_args(argv)
    isolate = (not args.no_isolate
               and "fork" in multiprocessing.get_all_start_methods())

    import convert
    from researchly import api
    from researchly.config import Config

    manifest = args.manifest or common.default_manifest()
    cache = common.outside_repo(args.cache or common.default_cache())
    out = common.outside_repo(args.out or common.default_out())
    index_path = cache / "index.json"
    if not index_path.exists():
        sys.exit(f"no {index_path}; run fetch.py first")
    index = {e["id"]: e for e in json.loads(index_path.read_text())["items"]}
    items = common.load_manifest(manifest)
    if args.only:
        items = [i for i in items if i["id"] in set(args.only)]
    if args.limit is not None:
        items = items[:args.limit]

    cfg = Config(grammar_tier=False if args.no_grammar else None)
    t_start = time.perf_counter()
    nlp = api.get_nlp()
    # Warm up (spaCy, SymSpell, LanguageTool's server) so the first file's
    # timing is not mostly start-up.
    t_warm = time.perf_counter()
    api.analyze("The engine is warming up before the first document.",
                nlp=nlp, cfg=cfg)
    warm_readers()
    install_watch()
    warm_s = round(time.perf_counter() - t_warm, 1)
    records: list[dict] = []
    samples: list[dict] = []
    health = None
    print(f"checking {len(items)} item(s); outputs in {out}")
    for item in items:
        entry = index.get(item["id"])
        status = entry["status"] if entry else "not_fetched"
        if status != "ok":
            records.append({"type": "item", "id": item["id"],
                            "format": item["format"], "status": status,
                            "error": (entry or {}).get("error")})
            continue
        try:
            renders = files_for(item, entry, cache)
        except (convert.ConvertError, OSError) as err:
            status = ("convert_error" if isinstance(err, convert.ConvertError)
                      else "cache_error")
            records.append({"type": "item", "id": item["id"],
                            "format": item["format"], "status": status,
                            "error": (str(err) if status == "convert_error"
                                      else type(err).__name__)})
            print(f"  {item['id']}: {status} ({records[-1]['error']})")
            continue
        allow = not args.no_samples and common.snippets_allowed(item)
        runs = {}
        for r in renders:
            if isolate:
                rec, analysis = run_isolated(item, r, cfg, args.read_timeout,
                                             args.analyze_timeout)
            else:
                rec, analysis = run_file(item, r, nlp, cfg)
            records.append(rec)
            if analysis is not None:
                health = health or analysis.health
                if r.name != "native":
                    runs[r.name] = (r, analysis)
                if allow:
                    collect_samples(item, rec, analysis, samples)
            fails = ",".join(sorted(rec.get("invariant_failures") or {}))
            print(f"  {item['id']:44s} {r.name:6s} {rec['status']:17s}"
                  + (f" {rec.get('prose_words', 0):>7,}w"
                     f" {rec.get('flags', 0):>5} flags"
                     f" {rec.get('per_1000', 0):>6}/1000w"
                     f" {rec.get('parse_s', 0) + rec.get('analyze_s', 0):6.1f}s"
                     if rec["status"] in ("ok", "invariant_failure") else
                     f" {rec.get('error_code') or rec.get('error_type')}")
                  + (f"  [{fails}]" if fails else ""))
        if len(runs) >= 2:
            records.append(parity(item, runs, args.parity_abs,
                                  args.parity_rel,
                                  samples if allow else None))

    grammar_seen = any(r.get("grammar_ok") for r in records
                       if r.get("type") == "doc")
    meta = {
        "manifest": (str(manifest.resolve().relative_to(common.REPO))
                     if common.REPO in manifest.resolve().parents
                     else manifest.name),
        "items": len(items),
        "grammar": "off" if args.no_grammar else (
            "running" if grammar_seen else "not running"),
        "require_grammar": args.require_grammar,
        "health": health or [],
        "seconds": round(time.perf_counter() - t_start, 1),
        "isolated": isolate,
        "timeouts_s": {"read": args.read_timeout,
                       "analyze": args.analyze_timeout},
        "warm_up_seconds": warm_s,
        "python": sys.version.split()[0],
        "parity_tolerance": {"abs": args.parity_abs, "rel": args.parity_rel},
        "samples_written": len(samples),
    }
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    with (out / "samples.jsonl").open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"done in {meta['seconds']} s; grammar {meta['grammar']}; "
          f"{len(samples)} sample(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
