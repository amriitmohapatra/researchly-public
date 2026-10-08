"""Shared plumbing for the real-document bench: manifest, paths, policy.

Nothing here touches document text. The rules that keep the bench from
leaking it live here so every script applies the same ones:

- cache and output directories must be OUTSIDE the repository
  (`outside_repo`), so a fetched article can never be committed by accident;
- snippets of document text may be written only for items whose licence
  allows redistribution (`snippets_allowed`), and only to samples.jsonl.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORE = REPO / "packages" / "core"

FORMATS = {"jats", "latex", "docx"}
SOURCES = {"europepmc", "biorxiv", "medrxiv", "arxiv", "github"}
KINDS = {"article", "preprint", "test-file"}
REQUIRED = ("id", "kind", "source", "format", "url", "licence",
            "permitted_use")

EXPECTS = {"parse", "error", "either"}

# Licences whose text may appear (as short snippets) in the CI artifact:
# CC BY and CC0 articles; Apache, MIT, BSD and MPL test files. Never NC or ND
# (nor SA) items: those need a reading of their terms we have not done.
_SNIPPET_LICENCES = re.compile(
    r"^(CC-BY(-[0-9.]+)?|CC0(-1\.0)?|Apache-2\.0|MIT|BSD-[23]-Clause|"
    r"MPL-2\.0)$", re.I)


class ManifestError(ValueError):
    pass


def default_manifest() -> Path:
    """manifest.yaml (the corpus builder's) when present, else the example."""
    real = HERE / "manifest.yaml"
    return real if real.exists() else HERE / "manifest.example.yaml"


def _base_dir() -> Path:
    return Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) \
        / "researchly-realdocs"


def default_cache() -> Path:
    return _base_dir() / "cache"


def default_out() -> Path:
    return _base_dir() / "out"


def outside_repo(path: Path) -> Path:
    """`path`, resolved, or exit if it lies inside the repository: fetched
    documents and samples must never be where `git add` can reach them."""
    p = Path(path).expanduser().resolve()
    if p == REPO or REPO in p.parents:
        sys.exit(f"refusing to use {p}: it is inside the repository. Fetched "
                 "documents and samples must live outside it (default: "
                 "$RUNNER_TEMP or the system temp dir).")
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_manifest(path: Path) -> list[dict]:
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if data.get("version") != 1:
        raise ManifestError(f"{path}: expected version: 1")
    items = data.get("items") or []
    seen: set[str] = set()
    for n, item in enumerate(items):
        where = f"{path} item {n}"
        missing = [k for k in REQUIRED if not item.get(k)]
        if missing:
            raise ManifestError(f"{where}: missing {', '.join(missing)}")
        if item["id"] in seen:
            raise ManifestError(f"{where}: duplicate id {item['id']}")
        seen.add(item["id"])
        if item["format"] not in FORMATS:
            raise ManifestError(f"{where}: format must be one of "
                                f"{sorted(FORMATS)}")
        if item["source"] not in SOURCES:
            raise ManifestError(f"{where}: source must be one of "
                                f"{sorted(SOURCES)}")
        if item["kind"] not in KINDS:
            raise ManifestError(f"{where}: kind must be one of "
                                f"{sorted(KINDS)}")
        if not isinstance(item["permitted_use"], list):
            raise ManifestError(f"{where}: permitted_use must be a list")
        if item.get("expect") is not None and item["expect"] not in EXPECTS:
            raise ManifestError(f"{where}: expect must be one of "
                                f"{sorted(EXPECTS)}")
        item.setdefault("notes", "")
        item["discipline"] = item.get("discipline") or "unknown"
    return items


def ci_permitted(item: dict) -> bool:
    return "ci_eval" in (item.get("permitted_use") or [])


_NOTE = re.compile(r"\b(pick|main)\s*:\s*([^\s;,]+)")


def notes_of(item: dict) -> dict[str, str]:
    """`notes: "pick: *.docx"` -> {"pick": "*.docx"}; also `main: <path>`
    (the main .tex of a LaTeX project, per the corpus builder)."""
    return {k: v for k, v in _NOTE.findall(str(item.get("notes") or ""))}


def expectation(item: dict) -> str | None:
    """What reading this file should do: "parse" (be read), "error" (be
    refused with an IngestError), "either"; None for ordinary documents,
    which must parse."""
    return item.get("expect")


def snippets_allowed(item: dict) -> bool:
    return bool(_SNIPPET_LICENCES.match(str(item.get("licence", "")).strip()))


def safe_name(text: str) -> str:
    """A file-system-safe version of an id or archive member name."""
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "item"
    if len(out) > 120:                # keep the extension: readers dispatch on it
        stem, dot, ext = out.rpartition(".")
        keep = "." + ext if dot and len(ext) <= 10 else ""
        out = out[:120 - len(keep)] + keep
    return out


def add_core_to_path() -> None:
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
