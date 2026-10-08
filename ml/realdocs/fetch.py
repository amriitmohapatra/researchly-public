"""Download the manifest's documents into a cache OUTSIDE the repository.

    python ml/realdocs/fetch.py [--manifest M] [--cache DIR] [--log FILE]

For each item whose `permitted_use` includes `ci_eval`, the payload is
downloaded once (politely: a contact User-Agent, a per-host minimum interval
of >= 3 s for arXiv, retries with back-off, a size cap) and turned into the
files the engine reads:

- format `jats`  -> `article.xml` (convert.py makes the three renderings);
- format `docx`  -> the .docx itself, or with `notes: "pick: *.docx"` the
  matching members of the zip the URL returns (Europe PMC
  supplementaryFiles);
- format `latex` -> a GitHub archive tarball (`.../archive/{sha}.tar.gz`,
  one top-level `{repo}-{sha}/` directory), an arXiv-style e-print (a
  gzipped single .tex, or a tar[.gz] project) or a bare .tex. A project
  becomes an in-memory `.zip` of its `.tex` files (a lone top-level
  directory is stripped; `.Rnw` files are included renamed to `.tex`), so it
  goes through `ingest.load_bytes("x.zip", ...)` exactly as an Overleaf
  download does. Archives are read in memory, never extracted.

Unavailable sources are skipped, not failed: Europe PMC answers 404 for
records that have not propagated yet, and bioRxiv/medRxiv answer 403 from
Cloudflare to automated clients. report.py shows how many were skipped.

`index.json` in the cache lists what each item produced; the run log
(`--log`, JSON lines) records every request with its sha256, size and
timing. Neither holds document text, and the manifest is never modified.

`--mirror PREFIX=DIR` serves URLs starting with PREFIX from a local
directory instead of the network (for sandboxes that cannot reach a host).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import http.client
import io
import json
import posixpath
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

USER_AGENT = ("ResearchlyRealDocs/1.0 (+https://github.com/amriitmohapatra/"
              "Researchly; automated weekly evaluation of a writing checker; "
              "low volume)")
MAX_BYTES = 200 * 1024 * 1024       # one download (repo tarballs carry figures)
MAX_UNPACKED = 50 * 1024 * 1024     # all .tex / picked members of one item
MAX_TEX_FILES = 200                 # ingest's own zip member cap
# Seconds between requests to one host. arXiv asks for no more than one
# request every 3 seconds; everyone else gets a polite 1 s.
HOST_INTERVAL = {"arxiv.org": 3.5, "export.arxiv.org": 3.5,
                 "www.ebi.ac.uk": 0.5, "raw.githubusercontent.com": 0.2}
DEFAULT_INTERVAL = 1.0
ATTEMPTS = 4
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class FetchError(Exception):
    """The download or unpacking failed; `status` goes in the index."""

    def __init__(self, message: str, status: str = "fetch_failed",
                 http: int | None = None):
        super().__init__(message)
        self.status = status
        self.http = http


# -- HTTP ------------------------------------------------------------------

class Limiter:
    def __init__(self):
        self.last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        gap = HOST_INTERVAL.get(host, DEFAULT_INTERVAL)
        due = self.last.get(host, 0.0) + gap
        now = time.monotonic()
        if due > now:
            time.sleep(due - now)
        self.last[host] = time.monotonic()


def _retry_after(err: urllib.error.HTTPError, attempt: int) -> float:
    value = err.headers.get("Retry-After") if err.headers else None
    if value and value.strip().isdigit():
        return min(float(value), 120.0)
    return min(5.0 * 2 ** attempt, 60.0)


def _read_capped(resp, cap: int) -> bytes:
    length = resp.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > cap:
        raise FetchError(f"larger than the {cap // 2**20} MB cap", "too_large")
    buf = bytearray()
    while True:
        chunk = resp.read(1 << 16)
        if not chunk:
            return bytes(buf)
        buf += chunk
        if len(buf) > cap:
            raise FetchError(f"larger than the {cap // 2**20} MB cap",
                             "too_large")


def http_get(url: str, limiter: Limiter, log, item_id: str,
             mirrors: list[tuple[str, Path]], cap: int = MAX_BYTES) -> bytes:
    matched = False
    for prefix, root in mirrors:
        if url.startswith(prefix):
            matched = True
            rel = urllib.parse.unquote(url[len(prefix):].split("?", 1)[0])
            path = (root / rel.lstrip("/")).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                continue
            data = path.read_bytes()
            log(item_id, url, "mirror", 200, data, 0.0)
            return data
    if matched:
        raise FetchError("not in the local mirror")
    host = urllib.parse.urlsplit(url).hostname or ""
    for attempt in range(ATTEMPTS):
        limiter.wait(host)
        t0 = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = _read_capped(resp, cap)
                log(item_id, url, "ok", resp.status, data,
                    time.monotonic() - t0)
                return data
        except urllib.error.HTTPError as err:
            log(item_id, url, "http_error", err.code, None,
                time.monotonic() - t0)
            if err.code in RETRY_STATUS and attempt < ATTEMPTS - 1:
                time.sleep(_retry_after(err, attempt))
                continue
            raise FetchError(f"HTTP {err.code}", http=err.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException) as err:
            log(item_id, url, "network_error", None, None,
                time.monotonic() - t0, type(err).__name__)
            if attempt < ATTEMPTS - 1:
                time.sleep(min(5.0 * 2 ** attempt, 60.0))
                continue
            raise FetchError(f"network error ({type(err).__name__})") \
                from None
    raise FetchError("retries exhausted")


# -- unpacking (in memory only) -----------------------------------------------

def _gunzip(data: bytes, cap: int = MAX_UNPACKED) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(data, cap + 1)
    except zlib.error:
        raise FetchError("damaged gzip stream", "unpack_failed") from None
    if len(out) > cap or d.unconsumed_tail:
        raise FetchError("gzip expands past the cap", "too_large")
    return out


def _member_name(name: str) -> str | None:
    """A normalised relative member path, or None if it escapes the root."""
    n = name.replace("\\", "/")
    if not n or n.startswith("/") or "\x00" in n or ":" in n.split("/")[0]:
        return None
    n = posixpath.normpath(n)
    if n == ".." or n.startswith("../"):
        return None
    return n


TEX_LIKE = (".tex", ".rnw")


def zip_name(member: str) -> str:
    """The name a project member gets in the zip: `.Rnw` (knitr/Sweave
    LaTeX) becomes `.tex`, since the zip adapter reads only `.tex`."""
    if member.lower().endswith(".rnw"):
        return member[:-4] + ".tex"
    return member


def _strip_top(names: list[str]) -> str:
    """The single top-level directory every name sits under ('' if none):
    GitHub archives wrap the repository in `{repo}-{sha}/`."""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        return tops.pop() + "/"
    return ""


def _pack_tex(entries: list) -> tuple[bytes, list[str]]:
    """[(member name, size, read())] of a project archive -> (an in-memory
    zip of its .tex/.Rnw files, notes). A lone top-level directory is
    stripped; paths outside the project are skipped."""
    notes: list[str] = []
    rel = [(re.sub(r"^(?:\./)+", "", n.replace("\\", "/")), size, read)
           for n, size, read in entries]
    top = _strip_top([n for n, _, _ in rel])
    tex_names = {n[len(top):] for n, _, _ in rel
                 if n.lower().endswith(".tex")}
    out = io.BytesIO()
    total = count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for raw, size, read in rel:
            if not raw.lower().endswith(TEX_LIKE):
                continue
            name = _member_name(raw[len(top):])
            if name is None:
                notes.append("skipped a member outside the project")
                continue
            if name.lower().endswith(".rnw"):
                if zip_name(name) in tex_names:
                    notes.append(f"{name} skipped: {zip_name(name)} exists")
                    continue
                notes.append(f"{name} (Sweave/knitr) included as "
                             f"{zip_name(name)}")
                name = zip_name(name)
            if count >= MAX_TEX_FILES:
                notes.append(f"more than {MAX_TEX_FILES} .tex files; "
                             "the rest were skipped")
                break
            total += size
            if total > MAX_UNPACKED:
                raise FetchError(".tex files expand past the cap",
                                 "too_large")
            body = read()
            if body is None:
                continue
            zf.writestr(name, body)
            count += 1
    if count == 0:
        raise FetchError("the archive has no .tex files", "no_source")
    if top:
        notes.append(f"stripped top-level directory {top}")
    return out.getvalue(), notes


def tex_zip_from_tar(data: bytes) -> tuple[bytes, list[str]] | None:
    """A tar (plain or compressed) -> _pack_tex's result, or None if `data`
    is not a tar archive. Only regular files are read: symlinks, devices
    and hard links are never followed."""
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except (tarfile.ReadError, EOFError, zlib.error, OSError):
        return None
    with tf:
        try:
            members = [m for m in tf.getmembers() if m.isfile()]
        except (tarfile.TarError, EOFError, zlib.error, OSError):
            raise FetchError("damaged tar archive", "unpack_failed") from None

        def reader(m):
            def read():
                f = tf.extractfile(m)
                return f.read() if f is not None else None
            return read
        try:
            return _pack_tex([(m.name, m.size, reader(m)) for m in members])
        except (tarfile.TarError, EOFError, zlib.error, OSError):
            raise FetchError("damaged tar archive", "unpack_failed") from None


def tex_zip_from_zip(data: bytes) -> tuple[bytes, list[str]]:
    """A project .zip (Overleaf download, GitHub zipball) repacked the same
    way, so figures and build output never count against ingest's limits."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = [i for i in zf.infolist() if not i.is_dir()
                 and not i.flag_bits & 0x1]
        return _pack_tex([(i.filename, i.file_size,
                           (lambda i=i: zf.read(i))) for i in infos])
    except (zipfile.BadZipFile, zlib.error, OSError, ValueError, EOFError,
            NotImplementedError):
        raise FetchError("damaged zip archive", "unpack_failed") from None


def prepare_latex(data: bytes, url_name: str) -> tuple[dict[str, bytes],
                                                      list[str]]:
    """Files to check from a LaTeX payload: an arXiv e-print (gzip of one
    .tex, or a tar[.gz] project), a .zip, or a bare .tex."""
    if data[:4] == b"%PDF":
        raise FetchError("no LaTeX source (the server sent a PDF)",
                         "no_source")
    if data[:2] == b"PK":
        packed, notes = tex_zip_from_zip(data)
        return {"project.zip": packed}, notes
    packed = tex_zip_from_tar(data)
    if packed is not None:
        return {"project.zip": packed[0]}, packed[1]
    if data[:2] == b"\x1f\x8b":
        inner = _gunzip(data)
        if inner[:4] == b"%PDF":
            raise FetchError("no LaTeX source (the e-print is a PDF)",
                             "no_source")
        return {"main.tex": inner}, ["gzipped single .tex"]
    name = url_name if url_name.lower().endswith((".tex", ".ltx")) \
        else "main.tex"
    return {name: data}, []


def prepare_docx(data: bytes, url_name: str, pick: str | None
                 ) -> tuple[dict[str, bytes], list[str]]:
    if not pick:
        name = url_name if url_name.lower().endswith(".docx") else \
            "document.docx"
        return {name: data}, []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        raise FetchError("expected a zip to pick members from",
                         "unpack_failed") from None
    files: dict[str, bytes] = {}
    notes: list[str] = []
    total = 0
    for info in infos:
        base = posixpath.basename(info.filename.replace("\\", "/"))
        if info.is_dir() or not fnmatch.fnmatch(base.lower(), pick.lower()):
            continue
        if info.flag_bits & 0x1:
            notes.append("skipped an encrypted member")
            continue
        total += info.file_size
        if total > MAX_UNPACKED:
            raise FetchError("picked members expand past the cap",
                             "too_large")
        try:
            body = zf.read(info)
        except (zipfile.BadZipFile, zlib.error, OSError, ValueError,
                NotImplementedError):
            notes.append("skipped a damaged member")
            continue
        name = common.safe_name(base)
        while name in files:
            name = "x_" + name
        files[name] = body
    if not files:
        raise FetchError(f"no member matches {pick}", "no_match")
    return files, notes


def prepare(item: dict, data: bytes) -> tuple[dict[str, bytes], list[str]]:
    url_name = posixpath.basename(urllib.parse.urlsplit(item["url"]).path)
    fmt = item["format"]
    if fmt == "jats":
        head = data.lstrip()[:200]
        if not (head.startswith(b"<?xml") or head.startswith(b"<!DOCTYPE")
                or head.startswith(b"<article")):
            raise FetchError("the response is not JATS XML", "no_source")
        return {"article.xml": data}, []
    if fmt == "latex":
        return prepare_latex(data, url_name)
    return prepare_docx(data, url_name, common.notes_of(item).get("pick"))


# -- driver -------------------------------------------------------------------

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_key(item: dict) -> str:
    """A cached fetch is reused only while everything that shaped it (URL,
    format, `pick:`/`main:` notes) is unchanged."""
    return sha256(json.dumps([item["url"], item["format"],
                              str(item.get("notes") or "")]).encode())


def fetch_all(items: list[dict], cache: Path, log_path: Path, *,
              mirrors: list[tuple[str, Path]], refresh: bool = False,
              quiet: bool = False) -> dict:
    limiter = Limiter()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    index = {"generated": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "items": []}

    with log_path.open("a", encoding="utf-8") as logf:
        def log(item_id, url, outcome, status, data, seconds, error=None):
            rec = {"time": datetime.now(timezone.utc).isoformat(
                       timespec="seconds"),
                   "id": item_id, "url": url, "outcome": outcome,
                   "http_status": status, "seconds": round(seconds, 2)}
            if data is not None:
                rec["bytes"] = len(data)
                rec["sha256"] = sha256(data)
            if error:
                rec["error"] = error
            logf.write(json.dumps(rec) + "\n")
            logf.flush()

        for item in items:
            entry = {"id": item["id"], "format": item["format"],
                     "url": item["url"]}
            index["items"].append(entry)
            if not common.ci_permitted(item):
                entry["status"] = "skipped_permitted_use"
                continue
            folder = cache / common.safe_name(item["id"])
            meta_path = folder / "meta.json"
            key = cache_key(item)
            if not refresh and meta_path.exists():
                old = json.loads(meta_path.read_text())
                if (old.get("key") == key and old.get("status") == "ok"
                        and all((folder / f["name"]).is_file()
                                for f in old.get("files", []))):
                    entry.update(old, cached=True)
                    log(item["id"], item["url"], "cached", None, None, 0.0)
                    continue
            try:
                data = http_get(item["url"], limiter, log, item["id"],
                                mirrors)
                files, notes = prepare(item, data)
            except FetchError as err:
                status = err.status
                if err.http == 404 and item["source"] == "europepmc":
                    status = "skipped_not_in_europepmc"
                elif err.http == 403 and item["source"] in ("biorxiv",
                                                            "medrxiv"):
                    status = "skipped_blocked_by_preprint_server"
                entry.update(status=status, error=str(err))
                if not quiet:
                    print(f"  {item['id']}: {status} ({err})")
                continue
            if folder.exists():             # never mix files from an old fetch
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            for name, body in files.items():
                (folder / name).write_bytes(body)
            entry.update(status="ok", key=key, sha256=sha256(data),
                         bytes=len(data),
                         files=[{"name": n, "bytes": len(b),
                                 "sha256": sha256(b)}
                                for n, b in files.items()],
                         notes=notes)
            meta_path.write_text(json.dumps(entry, indent=1))
            if not quiet:
                print(f"  {item['id']}: ok ({len(data):,} bytes, "
                      f"{len(files)} file(s))")
    (cache / "index.json").write_text(json.dumps(index, indent=1))
    return index


def _mirror(spec: str) -> tuple[str, Path]:
    prefix, sep, folder = spec.partition("=")
    if not sep or not prefix or not folder:
        raise argparse.ArgumentTypeError("use PREFIX=DIR")
    return prefix, Path(folder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--log", type=Path, default=None,
                    help="run log (JSON lines); default <cache>/fetch_log.jsonl")
    ap.add_argument("--only", nargs="*", default=None, help="item ids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--refresh", action="store_true",
                    help="download again even if cached")
    ap.add_argument("--mirror", type=_mirror, action="append", default=[],
                    metavar="PREFIX=DIR")
    args = ap.parse_args(argv)

    manifest = args.manifest or common.default_manifest()
    cache = common.outside_repo(args.cache or common.default_cache())
    log_path = args.log or cache / "fetch_log.jsonl"
    common.outside_repo(log_path.parent)
    items = common.load_manifest(manifest)
    if args.only:
        items = [i for i in items if i["id"] in set(args.only)]
    if args.limit is not None:
        items = items[:args.limit]
    print(f"fetching {len(items)} item(s) from {manifest.name} into {cache}")
    index = fetch_all(items, cache, log_path, mirrors=args.mirror,
                      refresh=args.refresh)
    resolved = manifest.resolve()
    index["manifest"] = (str(resolved.relative_to(common.REPO))
                         if common.REPO in resolved.parents else str(manifest))
    (cache / "index.json").write_text(json.dumps(index, indent=1))
    states: dict[str, int] = {}
    for e in index["items"]:
        states[e["status"]] = states.get(e["status"], 0) + 1
    print("fetch:", ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
    # Fetch problems are reported by report.py; only a run that fetched
    # nothing at all is an error here.
    return 0 if states.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
