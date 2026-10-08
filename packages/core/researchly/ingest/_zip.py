"""Opening an untrusted .zip (Overleaf project or .docx) in memory.

Everything is checked from the central directory before a byte is
decompressed. CPython's zipfile stops decompressing a member at its declared
size, so once the declared sizes pass, a member cannot expand past them.
Nothing is ever extracted to disk (ADR-02).
"""

from __future__ import annotations

import io
import posixpath
import re
import stat
import zipfile
import zlib

from . import IngestError

MAX_ENTRIES = 200
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_RATIO = 100
# A member this small cannot hurt under the total cap, and highly repetitive
# small files (a generated table of zeros) legitimately compress > 100x.
RATIO_FLOOR = 64 * 1024

_READ_ERRORS = (zipfile.BadZipFile, zlib.error, OSError, EOFError,
                ValueError, NotImplementedError, RuntimeError)


def open_zip(data: bytes, what: str) -> tuple[zipfile.ZipFile,
                                              dict[str, zipfile.ZipInfo]]:
    """The archive and its file members by normalised name. Raises
    IngestError for anything unsafe; `what` names the kind of file
    (".zip", ".docx") in messages, never the filename."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except _READ_ERRORS:
        raise IngestError("unreadable_file",
                          f"This {what} file could not be opened. Check that "
                          "it is not damaged or password-protected, and "
                          "upload it again.") from None
    if len(infos) > MAX_ENTRIES:
        raise IngestError("payload_too_large",
                          f"This {what} file has more than {MAX_ENTRIES} "
                          "files in it. Remove output files and images, or "
                          "upload the .tex files only.")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise IngestError("payload_too_large",
                          f"This {what} file expands to more than "
                          f"{MAX_UNCOMPRESSED // (1024 * 1024)} MB.")
    members: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        if info.flag_bits & 0x1:
            raise IngestError("unreadable_file",
                              f"This {what} file is password-protected. "
                              "Remove the password and upload it again.")
        if (info.file_size > RATIO_FLOOR
                and info.file_size > MAX_RATIO * max(info.compress_size, 1)):
            raise IngestError("payload_too_large",
                              f"This {what} file contains a member that "
                              "expands more than a real document would, so "
                              "it was not opened.")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise IngestError("unreadable_file",
                              f"This {what} file contains a symbolic link, "
                              "which Researchly does not follow.")
        name = info.filename.replace("\\", "/")
        if (name.startswith("/") or re.match(r"[A-Za-z]:", name)
                or ".." in name.split("/") or "\x00" in name):
            raise IngestError("unreadable_file",
                              f"This {what} file contains a path outside the "
                              "project, so it was not opened.")
        if not info.is_dir():
            members[posixpath.normpath(name)] = info
    return zf, members


def read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo,
                what: str) -> bytes:
    try:
        return zf.read(info)
    except _READ_ERRORS:
        raise IngestError("unreadable_file",
                          f"Part of this {what} file is damaged and could "
                          "not be read.") from None
