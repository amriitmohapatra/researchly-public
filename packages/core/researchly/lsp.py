"""Researchly Language Server (LSP) — suggestions inside your editor.

Run:  python3 -m researchly.lsp        (communicates over stdio)

Works with any LSP client: the bundled VS Code extension (word-addin's
sibling in vscode-extension/), Neovim, Helix, Emacs, Zed, Positron.

What it does:
- On open/change (debounced ~600 ms), checks .qmd / .md / .Rmd / .tex /
  plain-text documents with the same engine as the CLI and Word add-in.
- Publishes diagnostics: severity encodes the suggestion type
  (Correction → Warning, Improvement → Information, Convention →
  Information, Preference → Hint), the code is the rule id, and the
  message carries the one-line reason (+ the full "why" available via
  the code description in clients that show it).
- Quick fixes: suggestions with a concrete replacement become code
  actions; every diagnostic also gets a "mute rule in .researchly.toml"
  action that edits the project config file.
- Reads `.researchly.toml` next to the file (or in the workspace root):
  disabled rules and show_preferences, exactly like the CLI.

Everything runs locally; nothing leaves the machine. All analysis is
synchronous CPU work on small documents — the debounce keeps it snappy.
"""

from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp

from pygls.server import LanguageServer

from . import api
from . import config as config_mod
from .document import Document
from .engine import REGISTRY, Category, check
from . import (rules_lexical, rules_syntax,  # noqa: F401  (register)
               rules_spelling, rules_grammar)

DEBOUNCE_S = 0.6

SEVERITY = {
    Category.CORRECTION: lsp.DiagnosticSeverity.Warning,
    Category.IMPROVEMENT: lsp.DiagnosticSeverity.Information,
    Category.CONVENTION: lsp.DiagnosticSeverity.Information,
    Category.PREFERENCE: lsp.DiagnosticSeverity.Hint,
}

KIND_BY_EXT = {
    ".md": "markdown", ".qmd": "markdown", ".rmd": "markdown",
    ".markdown": "markdown", ".tex": "latex", ".ltx": "latex",
}


class ResearchlyServer(LanguageServer):
    def __init__(self):
        super().__init__("researchly-lsp", "0.2.0")
        self._nlp = None
        self._nlp_lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self.closed: set[str] = set()
        # last published suggestions per uri, for code actions
        self.last: dict[str, list] = {}

    @property
    def nlp(self):
        with self._nlp_lock:
            if self._nlp is None:
                # The shared, identically configured pipeline (P33).
                from .api import get_nlp
                self._nlp = get_nlp()
        return self._nlp

    def cancel(self, uri: str):
        old = self._timers.pop(uri, None)
        if old:
            old.cancel()

    def schedule(self, uri: str):
        self.closed.discard(uri)
        old = self._timers.pop(uri, None)
        if old:
            old.cancel()
        t = threading.Timer(DEBOUNCE_S, self.run_check, args=(uri,))
        t.daemon = True
        self._timers[uri] = t
        t.start()

    def run_check(self, uri: str):
        try:
            text_doc = self.workspace.get_text_document(uri)
            version = getattr(text_doc, "version", None)
            path = Path(unquote(urlparse(uri).path))
            kind = KIND_BY_EXT.get(path.suffix.lower(), "plain")
            analysis = api.analyze(text_doc.source, kind=kind, nlp=self.nlp,
                                   near=path, with_metrics=False)
            doc = analysis.document
            doc.path = str(path)

            suggestions = analysis.suggestions
            # An edit or a close while the check ran makes these results
            # stale: never publish an older document's diagnostics.
            if uri in self.closed or getattr(
                    self.workspace.get_text_document(uri), "version",
                    None) != version:
                return
            self.last[uri] = suggestions
            self.publish_diagnostics(
                uri, [to_diagnostic(s, doc) for s in suggestions])
        except Exception as e:  # never crash the editor session
            self.show_message_log(f"researchly check failed: {e}",
                                  lsp.MessageType.Warning)


def to_position(doc: Document, offset: int) -> lsp.Position:
    """LSP positions count UTF-16 code units (the protocol's default
    encoding, which VS Code uses); Python offsets count code points. After
    an emoji or a mathematical letter the two differ (Codex review R7)."""
    line, col = doc.line_col(offset)          # 1-based, code points
    prefix = doc.original[offset - (col - 1):offset]
    return lsp.Position(line=line - 1,
                        character=len(prefix.encode("utf-16-le")) // 2)


def to_range(doc: Document, s) -> lsp.Range:
    return lsp.Range(start=to_position(doc, s.start),
                     end=to_position(doc, s.end))


def to_diagnostic(s, doc: Document) -> lsp.Diagnostic:
    rule = REGISTRY[s.rule_id]
    section = f" · §{s.section}" if s.section != "unknown" else ""
    return lsp.Diagnostic(
        range=to_range(doc, s),
        severity=SEVERITY[s.category],
        code=s.rule_id,
        code_description=None,
        source="researchly",
        message=f"[{s.category.value}] {s.message}{section}\n"
                f"({s.rule_id} {rule.name} — `researchly explain "
                f"{s.rule_id}` for the full why)",
        data={"replacement": s.replacement, "start": s.start, "end": s.end,
              "rule_id": s.rule_id},
    )


server = ResearchlyServer()


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: ResearchlyServer, params: lsp.DidOpenTextDocumentParams):
    ls.schedule(params.text_document.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: ResearchlyServer, params: lsp.DidChangeTextDocumentParams):
    ls.schedule(params.text_document.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: ResearchlyServer, params: lsp.DidSaveTextDocumentParams):
    ls.schedule(params.text_document.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: ResearchlyServer, params: lsp.DidCloseTextDocumentParams):
    ls.cancel(params.text_document.uri)
    ls.closed.add(params.text_document.uri)
    ls.publish_diagnostics(params.text_document.uri, [])
    ls.last.pop(params.text_document.uri, None)


@server.feature(lsp.TEXT_DOCUMENT_CODE_ACTION,
                lsp.CodeActionOptions(code_action_kinds=[
                    lsp.CodeActionKind.QuickFix]))
def code_action(ls: ResearchlyServer, params: lsp.CodeActionParams):
    uri = params.text_document.uri
    actions: list[lsp.CodeAction] = []
    for diag in params.context.diagnostics:
        if diag.source != "researchly" or not isinstance(diag.data, dict):
            continue
        data = diag.data
        repl = data.get("replacement")
        if repl is not None:
            title = (f"Researchly: replace with '{repl}'" if repl
                     else "Researchly: delete this phrase")
            actions.append(lsp.CodeAction(
                title=title,
                kind=lsp.CodeActionKind.QuickFix,
                diagnostics=[diag],
                edit=lsp.WorkspaceEdit(changes={uri: [
                    lsp.TextEdit(range=diag.range, new_text=repl)]}),
            ))
        rule_id = data.get("rule_id") or diag.code
        actions.append(lsp.CodeAction(
            title=f"Researchly: mute rule {rule_id} everywhere",
            kind=lsp.CodeActionKind.QuickFix,
            diagnostics=[diag],
            command=lsp.Command(
                title="mute", command="researchly.muteRule",
                arguments=[uri, str(rule_id)]),
        ))
    return actions


@server.command("researchly.muteRule")
def mute_rule(ls: ResearchlyServer, args):
    """Mute through the shared config so every surface honours it.

    This used to hand-patch the project `.researchly.toml` with a literal
    `content.replace('disable = [', ...)`, which silently appended a second
    `[rules]` table whenever the file wrote `disable=[` or spread the array
    over several lines — and `if rule_id in content` matched the id anywhere,
    including inside a comment. It also wrote the PROJECT file, so a mute
    stuck to whichever folder you happened to be in.
    """
    uri, rule_id = args[0], args[1]
    path = Path(unquote(urlparse(uri).path))
    try:
        if not config_mod.mute_rule(str(rule_id), near=path):
            raise OSError("could not write the user config")
        ls.show_message(f"Researchly: muted {rule_id} "
                        f"(~/.researchly/config.toml — applies everywhere)")
        ls.schedule(uri)
    except Exception as e:
        ls.show_message(f"Researchly: could not mute {rule_id}: {e}",
                        lsp.MessageType.Warning)


def main():
    server.start_io()


if __name__ == "__main__":
    main()
