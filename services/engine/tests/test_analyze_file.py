"""/v1/analyze-file (S2): uploads read in memory, spans index document.text.

Synthetic text only (CLAUDE.md): never thesis or course passages.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

from conftest import PREFERENCE_TEXT

MD = ("# Methods\n\nThe model was calibrated by the authors using weekly data.\n\n"
      "# Discussion\n\nThe effect was very large in every district.\n")


def upload(c, data, name="chapter.md", ctype="application/octet-stream",
           options=None, headers=None):
    h = {"content-type": ctype,
         "x-researchly-filename": urllib.parse.quote(name)}
    if options is not None:
        h["x-researchly-options"] = json.dumps(options)
    h.update(headers or {})
    return c.post("/v1/analyze-file", content=data, headers=h)


def test_markdown_upload_returns_the_text_its_spans_index(client):
    r = upload(client, MD.encode(), options={"show_preferences": True})
    assert r.status_code == 200, r.text
    body = r.json()
    doc = body["document"]
    assert doc["filename"] == "chapter.md" and doc["format"] == "markdown"
    assert doc["text"] == MD
    assert doc["segments"] == [{"path": "chapter.md", "start": 0,
                                "end": len(MD), "source_start": 0}]
    assert body["suggestions"], "expected at least one suggestion"
    for s in body["suggestions"]:
        assert doc["text"][s["span"]["start"]:s["span"]["end"]] == s["text"]
    # Section-awareness survives upload: passive in Methods is not flagged.
    assert "methods" in body["sections_detected"]
    assert "W204" in {s["rule_id"] for s in body["suggestions"]}


def test_utf8_bom_and_non_ascii_filename(client):
    name = "Kapitel_ü draft.txt"
    r = upload(client, b"\xef\xbb\xbf" + PREFERENCE_TEXT.encode(), name=name)
    assert r.status_code == 200, r.text
    assert r.json()["document"]["filename"] == name
    assert r.json()["document"]["text"] == PREFERENCE_TEXT


@pytest.mark.parametrize("data,name,status,code", [
    (b"x", "chapter.pdf", 415, "unsupported_file"),
    (b"x", "noextension", 415, "unsupported_file"),
    (b"\xff\xfe\x00bad", "chapter.tex", 422, "unreadable_file"),
    (b"", "chapter.md", 422, "invalid_request"),
])
def test_unreadable_or_unsupported_files(client, data, name, status, code):
    r = upload(client, data, name=name)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code


def test_body_must_be_octet_stream(client):
    r = upload(client, MD.encode(), ctype="multipart/form-data; boundary=x")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"


def test_filename_header_is_required(client):
    r = client.post("/v1/analyze-file", content=MD.encode(),
                    headers={"content-type": "application/octet-stream"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("raw", ["%00evil.md", "%FFevil.md", "a" * 300 + ".md"])
def test_bad_filenames_are_refused_without_echo(client, raw):
    r = client.post("/v1/analyze-file", content=MD.encode(), headers={
        "content-type": "application/octet-stream",
        "x-researchly-filename": raw})
    assert r.status_code == 422
    assert "evil" not in r.text


def test_path_in_filename_is_reduced_to_the_name(client):
    r = upload(client, MD.encode(), name="../../etc/chapter.md")
    assert r.status_code == 200
    assert r.json()["document"]["filename"] == "chapter.md"


def test_bad_options_header(client):
    r = client.post("/v1/analyze-file", content=MD.encode(), headers={
        "content-type": "application/octet-stream",
        "x-researchly-filename": "chapter.md",
        "x-researchly-options": '{"secret_field_name": 1}'})
    assert r.status_code == 422
    assert "secret_field_name" not in r.text
    r = client.post("/v1/analyze-file", content=MD.encode(), headers={
        "content-type": "application/octet-stream",
        "x-researchly-filename": "chapter.md",
        "x-researchly-options": "{not json"})
    assert r.status_code == 422


def test_upload_cap_is_separate_from_the_json_cap(make_client):
    c = make_client(max_body_bytes=2048, max_upload_bytes=64 * 1024)
    big = (PREFERENCE_TEXT + "\n\n") * 100          # ~5 KB
    assert upload(c, big.encode()).status_code == 200
    r = c.post("/v1/analyze", json={"content": big})
    assert r.status_code == 413
    r = upload(c, b"x" * (65 * 1024))
    assert r.status_code == 413
    assert "MB" in r.json()["error"]["message"]


def test_files_need_an_account_when_accounts_are_on(make_client):
    c = make_client(supabase_url="https://abcdefghijklmnop.supabase.co",
                    supabase_publishable_key="sb_publishable_x")
    r = upload(c, MD.encode())
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "sign_in_required"


def test_docx_and_zip_are_routed_to_their_adapters(client):
    # Not a real archive: the adapter must refuse it cleanly, not 500.
    for name in ("chapter.docx", "project.zip"):
        r = upload(client, b"PK\x03\x04 not really a zip", name=name)
        assert r.status_code in (415, 422), (name, r.text)
        assert r.json()["error"]["code"] in ("unsupported_file", "unreadable_file")


# --- real .docx and Overleaf .zip, end to end (S2 adapters) -----------------
# The fixture builders live with the adapter tests in packages/core/tests.

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / "packages/core/tests"))
from ingest_fixtures import docx_bytes, para, run, zip_bytes  # noqa: E402

PASSIVE = "The model was calibrated by the authors using weekly data."


def test_docx_upload_end_to_end(client):
    body = (para(run("Methods"), style="Heading1") + para(run(PASSIVE))
            + para(run("Discussion"), style="Heading1")
            + para(run("The effect was very large in every district.")))
    r = upload(client, docx_bytes(body), name="chapter.docx",
               options={"show_preferences": True})
    assert r.status_code == 200, r.text
    b = r.json()
    doc = b["document"]
    assert doc["format"] == "docx"
    assert "Methods" in doc["text"] and PASSIVE in doc["text"]
    assert {"methods", "discussion"} <= set(b["sections_detected"])
    for s in b["suggestions"]:
        assert doc["text"][s["span"]["start"]:s["span"]["end"]] == s["text"]
    assert "W204" in {s["rule_id"] for s in b["suggestions"]}


def test_overleaf_zip_end_to_end(client):
    main = ("\\documentclass{article}\n\\begin{document}\n"
            "\\section{Methods}\n\\input{sections/results}\n\\end{document}\n")
    child = "\\section{Results}\nThe effect was very large in every district.\n"
    r = upload(client, zip_bytes({"main.tex": main, "sections/results.tex": child}),
               name="project.zip", options={"show_preferences": True})
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    assert doc["format"] == "latex"
    paths = [g["path"] for g in doc["segments"]]
    assert "main.tex" in paths and "sections/results.tex" in paths
    (w204,) = [s for s in r.json()["suggestions"] if s["rule_id"] == "W204"]
    seg = next(g for g in doc["segments"]
               if g["start"] <= w204["span"]["start"] < g["end"])
    assert seg["path"] == "sections/results.tex"
    off = seg["source_start"] + w204["span"]["start"] - seg["start"]
    assert child[off:off + 4] == "very"


def test_zip_warning_is_returned(client):
    main = ("\\documentclass{article}\n\\begin{document}\n"
            "Text.\n\\input{appendix}\n\\end{document}\n")
    r = upload(client, zip_bytes({"main.tex": main}), name="p.zip")
    assert r.status_code == 200
    assert any("appendix" in w for w in r.json()["document"]["warnings"])


def test_pasted_latex_fallback_is_visible(client):
    # Unbalanced braces send the parser to the regex fallback: say so.
    r = client.post("/v1/analyze", json={
        "format": "latex",
        "content": "\\section{Results}\nThe effect {was large in every district.\n"})
    assert r.status_code == 200
    assert r.json()["warnings"], "a parse fallback must not be silent"


def test_internal_structure_kinds_are_not_returned(client):
    # S2b records \ref and \label for the cross-reference checks; the
    # contract only lists what a reader sees.
    src = ("\\documentclass{article}\n\\begin{document}\n"
           "\\section{Results}\\label{sec:r}\nSee Figure~\\ref{fig:a}.\n"
           "\\begin{figure}\\caption{Weekly cases in every district.}"
           "\\label{fig:a}\\end{figure}\n\\end{document}\n")
    r = upload(client, src.encode(), name="chapter.tex")
    assert r.status_code == 200, r.text
    kinds = {s["kind"] for s in r.json()["document"]["structure"]}
    assert kinds <= {"figure", "table", "equation", "caption", "citation"}
    assert "figure" in kinds
