#!/bin/bash
# Build Researchly.app (and optionally a .dmg) on your Mac.
#
#   bash build_app.sh          # full standalone build (large, portable)
#   bash build_app.sh --alias  # fast dev build linked to this folder
#
# Prereqs (one-time):  pip3 install -r requirements-desktop.txt

set -e
cd "$(dirname "$0")"

# Use the interpreter that actually has the dependencies. Bare `python3` on
# this Mac is Homebrew 3.14 with no py2app and no spaCy, so the build failed
# immediately; the project runs on 3.10. Override with PYTHON=... if needed.
PYTHON="${PYTHON:-python3.10}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found. Set PYTHON=/path/to/python and retry." >&2
  exit 1
fi
if ! "$PYTHON" -c "import py2app" >/dev/null 2>&1; then
  echo "error: $PYTHON has no py2app." >&2
  echo "       $PYTHON -m pip install -r requirements-desktop.txt" >&2
  exit 1
fi

MODE=""
if [ "$1" = "--alias" ]; then
  MODE="-A"
  echo "Building in ALIAS mode (fast; app links to this folder — NOT"
  echo "portable to another Mac, so never ship an alias build)."
fi

# LanguageTool needs a real JRE. Ask the engine, not the shell: Homebrew's
# openjdk is keg-only, so `java` on PATH is Apple's stub even when a perfectly
# good JDK is installed. health.find_java() searches the filesystem (and so
# works for Finder-launched apps, which get no shell PATH at all).
if ! "$PYTHON" -c "import sys; sys.path.insert(0,'../../packages/core'); \
from researchly.health import find_java; sys.exit(0 if find_java() else 1)" \
  2>/dev/null; then
  echo "warning: no Java 17+ runtime found, so the built app's grammar tier" >&2
  echo "         (LT001) will be inactive. The app SAYS so rather than" >&2
  echo "         checking less than it claims. To enable it:" >&2
  echo "           brew install openjdk@17" >&2
  echo "         No symlink needed — a keg-only install is found." >&2
  echo >&2
fi

rm -rf build dist
"$PYTHON" setup.py py2app $MODE

echo
echo "Built: dist/Researchly.app"
echo "  • First launch: right-click → Open (unsigned app)."
echo "  • Grant Accessibility permission to Researchly when prompted."
echo "  • To make a .dmg:  bash make_dmg.sh"
