"""File adapters: bytes of an uploaded or local file -> one `Document`.

Every surface that accepts a *file* (the hosted engine's /v1/analyze-file,
the CLI) goes through `load_bytes`, so a format is read the same way
everywhere (ADR-04, docs/s2-design.md §4).

Contract:
- `load_bytes(filename, data)` returns a Document whose `segments` cover
  `original` and map every span back to a source file and offset.
- Anything wrong with the file raises `IngestError(code, message)`. The
  message is shown to the user, so it names the problem and never quotes
  document text.
- TeX is never executed; archives are never extracted to disk.
"""

from __future__ import annotations

from bisect import bisect_right
from pathlib import PurePosixPath

from ..document import Document, Segment

# A 150k-word thesis is ~1M characters (mirrors the service's MAX_CONTENT_CHARS).
MAX_TEXT_CHARS = 1_000_000

TEXT_SUFFIXES = {".md": "markdown", ".qmd": "markdown", ".rmd": "markdown",
                 ".markdown": "markdown", ".tex": "latex", ".ltx": "latex",
                 ".txt": "plain"}
SUFFIXES = sorted(set(TEXT_SUFFIXES) | {".docx", ".zip"})


class IngestError(ValueError):
    """A file that cannot be read. `code` is stable; `message` is user-safe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def suffix_of(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def decode_text(data: bytes, what: str = "The file") -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestError("unreadable_file",
                          f"{what} is not UTF-8 text. Save it as UTF-8 and "
                          "upload it again.") from None
    if len(text) > MAX_TEXT_CHARS:
        raise IngestError("payload_too_large",
                          f"{what} has more than {MAX_TEXT_CHARS:,} characters. "
                          "Check one chapter at a time.")
    return text


def from_text_file(filename: str, data: bytes, kind: str) -> Document:
    text = decode_text(data)
    doc = Document.from_text(text, kind)
    doc.path = filename
    doc.segments = [Segment(path=filename, start=0, end=len(text))]
    return doc


def source_position(segments: list[Segment], text: str,
                    offset: int) -> tuple[str, int, int]:
    """(path, 1-based line, 1-based column) of `offset` in its source file.

    A file split around its `\\input`s appears as several segments; the
    pieces of the same file before this one (same path, abutting source
    ranges) supply the lines above it.
    """
    if not segments:
        before = text[:offset]
        return "", before.count("\n") + 1, offset - before.rfind("\n")
    i = max(0, bisect_right([s.start for s in segments], offset) - 1)
    seg = segments[i]
    pieces = [text[seg.start:offset]]
    want = seg.source_start
    for s in reversed(segments[:i]):
        if want <= 0:
            break
        if s.path == seg.path and s.source_start + (s.end - s.start) == want:
            pieces.append(text[s.start:s.end])
            want = s.source_start
    before = "".join(reversed(pieces))
    return seg.path, before.count("\n") + 1, len(before) - before.rfind("\n")


def load_bytes(filename: str, data: bytes) -> Document:
    """Read one uploaded file. Dispatches on the extension only."""
    suffix = suffix_of(filename)
    if suffix == ".docx":
        from .docx import load_docx
        return load_docx(filename, data)
    if suffix == ".zip":
        from .latex_project import load_zip
        return load_zip(filename, data)
    if suffix in TEXT_SUFFIXES:
        return from_text_file(filename, data, TEXT_SUFFIXES[suffix])
    raise IngestError("unsupported_file",
                      "Researchly reads .docx, .tex, Overleaf .zip, .md, .qmd, "
                      ".Rmd and .txt files.")
