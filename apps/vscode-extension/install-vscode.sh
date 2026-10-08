#!/bin/bash
# Install the Researchly extension into VS Code (and Positron, if present)
# by copying it into the editor's extensions folder. No npm needed — the
# extension is pre-bundled in dist/.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="0.2.0"

install_to () {
  local EXTDIR="$1"
  [ -d "$(dirname "$EXTDIR")" ] || return 0
  local DEST="$EXTDIR/researchly-local.researchly-lsp-$VERSION"
  mkdir -p "$DEST/dist"
  cp "$HERE/package.json" "$DEST/"
  cp "$HERE/dist/extension.js" "$DEST/dist/"
  echo "installed -> $DEST"
}

install_to "$HOME/.vscode/extensions"
install_to "$HOME/.positron/extensions"

echo
echo "Now restart VS Code (or Positron). Open a .qmd/.md/.tex file and"
echo "underlines appear after a moment (first check loads the spaCy model)."
echo
echo "One-time server dependency (in your usual Python):"
echo "    pip install 'pygls>=1.3,<2'"
echo
echo "If your engine folder is not ~/Documents/Researchly/packages/core, or"
echo "your Python is not 'python3', set researchly.prototypePath /"
echo "researchly.pythonPath in VS Code Settings."
