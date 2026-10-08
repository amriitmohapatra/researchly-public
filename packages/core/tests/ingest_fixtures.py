"""Synthetic file builders for the ingest tests.

Every fixture is built in memory from sentences written for these tests:
no thesis, course or book text (ml/tools/check_third_party.py enforces it).
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Default Extension="xml" ContentType="application/xml"/>'
    '</Types>')

# Ids are what a German Word writes; names are the English built-ins.
STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W}">
  <w:style w:type="paragraph" w:styleId="Standard"><w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="berschrift1">
    <w:name w:val="heading 1"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Beschriftung">
    <w:name w:val="caption"/></w:style>
  <w:style w:type="paragraph" w:styleId="Kapitel">
    <w:name w:val="Kapitel"/><w:basedOn w:val="berschrift1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Titel"><w:name w:val="Title"/>
  </w:style>
</w:styles>"""


def zip_bytes(files: dict[str, bytes | str], *,
              compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def run(text: str, *, hidden: bool = False) -> str:
    rpr = "<w:rPr><w:vanish/></w:rPr>" if hidden else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(*content: str, style: str | None = None,
         outline: int | None = None) -> str:
    ppr = ""
    if style or outline is not None:
        ppr = "<w:pPr>"
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if outline is not None:
            ppr += f'<w:outlineLvl w:val="{outline}"/>'
        ppr += "</w:pPr>"
    body = "".join(c if c.startswith("<") else run(c) for c in content)
    return f"<w:p>{ppr}{body}</w:p>"


def deleted(text: str) -> str:
    return ('<w:del w:id="1" w:author="A" w:date="2026-01-01T00:00:00Z">'
            f'<w:r><w:delText xml:space="preserve">{escape(text)}</w:delText>'
            '</w:r></w:del>')


def inserted(text: str) -> str:
    return ('<w:ins w:id="2" w:author="A" w:date="2026-01-01T00:00:00Z">'
            f"{run(text)}</w:ins>")


def field(code: str, result: str) -> str:
    """A complex field (how Zotero and EndNote store a citation)."""
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{escape(code)}'
            '</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f"{run(result)}"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def equation(text: str) -> str:
    return f"<m:oMath><m:r><m:t>{escape(text)}</m:t></m:r></m:oMath>"


def drawing() -> str:
    return ('<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing>'
            '<w:txbxContent><w:p><w:r><w:t>boxtext</w:t></w:r></w:p>'
            '</w:txbxContent></w:drawing></mc:Choice><mc:Fallback><w:pict/>'
            '</mc:Fallback></mc:AlternateContent></w:r>')


def table(rows: list[list[str]]) -> str:
    out = "<w:tbl><w:tblPr/>"
    for r in rows:
        out += "<w:tr>" + "".join(
            f"<w:tc><w:tcPr/>{para(c)}</w:tc>" for c in r) + "</w:tr>"
    return out + "</w:tbl>"


def document_xml(body: str, prolog: str = "") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>{prolog}'
            f'<w:document xmlns:w="{W}" xmlns:m="{M}" xmlns:mc="{MC}">'
            f"<w:body>{body}<w:sectPr/></w:body></w:document>")


def docx_bytes(body: str, *, styles: str | None = STYLES,
               prolog: str = "", extra: dict | None = None) -> bytes:
    files: dict[str, bytes | str] = {
        "[Content_Types].xml": CONTENT_TYPES,
        "word/document.xml": document_xml(body, prolog),
    }
    if styles is not None:
        files["word/styles.xml"] = styles
    files.update(extra or {})
    return zip_bytes(files)


def set_encrypted_flag(data: bytes) -> bytes:
    """Mark every member as encrypted, as a password-protected zip is."""
    out = bytearray(data)
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = out.find(sig)
        while i != -1:
            out[i + off] |= 0x01
            i = out.find(sig, i + 4)
    return bytes(out)
