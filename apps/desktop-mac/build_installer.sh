#!/bin/bash
# Build the STANDALONE Researchly installer for macOS — every dependency
# inside the artifact: Python runtime + engine + spaCy model (py2app),
# LanguageTool pre-downloaded, and a trimmed private JRE (jlink).
# An installed app needs NO Python, NO Java, NO first-run download.
#
#   bash build_installer.sh            # → dist/Researchly.app
#                                        → Researchly-<v>.dmg  (drag-install)
#                                        → Researchly-<v>.pkg  (double-click installer)
#
# Options:
#   --skip-jre        don't bundle a JRE (grammar tier then needs system Java)
#   --skip-lt         don't bundle LanguageTool (downloads on first use)
#   --dmg-only / --pkg-only
#
# Prereqs on the BUILD Mac (testers need none of these):
#   pip3.10 install -r requirements.txt -r desktop-mac/requirements-desktop.txt
#   python3.10 -m spacy download en_core_web_sm
#   brew install openjdk@17        (or any JDK >= 17, for jlink + the JRE)
#
# Signing: artifacts are ad-hoc signed — fine for personal sharing
# (testers right-click → Open once). Wider distribution needs an Apple
# Developer ID; see the note at the end of this script's output.

set -euo pipefail
cd "$(dirname "$0")"

VERSION="0.8"
SKIP_JRE=0; SKIP_LT=0; MAKE_DMG=1; MAKE_PKG=1
for arg in "$@"; do
  case "$arg" in
    --skip-jre) SKIP_JRE=1 ;;
    --skip-lt)  SKIP_LT=1 ;;
    --dmg-only) MAKE_PKG=0 ;;
    --pkg-only) MAKE_DMG=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# --- interpreter (same logic as build_app.sh) ------------------------------
PYTHON="${PYTHON:-python3.10}"
command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "error: $PYTHON not found. Set PYTHON=/path/to/python and retry." >&2
  exit 1; }
for mod in py2app spacy en_core_web_sm symspellpy language_tool_python; do
  "$PYTHON" -c "import $mod" >/dev/null 2>&1 || {
    echo "error: $PYTHON is missing '$mod'." >&2
    echo "       $PYTHON -m pip install -r ../../packages/core/requirements.txt -r requirements-desktop.txt" >&2
    echo "       $PYTHON -m spacy download en_core_web_sm" >&2
    exit 1; }
done

# --- vendor/ : the bundled third-party runtimes ----------------------------
echo "==> preparing vendor/ (bundled dependencies)"
rm -rf vendor && mkdir -p vendor

if [ "$SKIP_LT" = 0 ]; then
  # Reuse the build machine's cached LanguageTool if present; download
  # (verified by language_tool_python's own SHA256 manifest) if not.
  CACHED=$(ls -d "$HOME/.cache/language_tool_python/LanguageTool"* 2>/dev/null | sort | tail -1 || true)
  if [ -n "$CACHED" ]; then
    echo "    LanguageTool: copying cached $(basename "$CACHED")"
    cp -R "$CACHED" vendor/
  else
    echo "    LanguageTool: downloading (~259 MB, one-time on this build Mac)"
    LTP_PATH="$PWD/vendor" "$PYTHON" - << 'PYEOF'
from language_tool_python.download_lt import download_lt
download_lt()
PYEOF
  fi
  LT_DIR=$(ls -d vendor/LanguageTool* | sort | tail -1)
  [ -f "$LT_DIR/languagetool-server.jar" ] || {
    echo "error: $LT_DIR has no languagetool-server.jar" >&2; exit 1; }
  echo "    LanguageTool bundled: $(basename "$LT_DIR")"
fi

if [ "$SKIP_JRE" = 0 ]; then
  # jlink a minimal private JRE from the build machine's JDK.
  JAVA_BIN=$("$PYTHON" -c "import sys; sys.path.insert(0,'../../packages/core'); \
from researchly.health import find_java; print(find_java() or '')")
  [ -n "$JAVA_BIN" ] || {
    echo "error: no JDK >= 17 found for jlink. brew install openjdk@17" >&2
    echo "       (or rerun with --skip-jre to require system Java at runtime)" >&2
    exit 1; }
  JLINK="$(dirname "$JAVA_BIN")/jlink"
  [ -x "$JLINK" ] || {
    echo "error: $JLINK not found — the discovered Java is a JRE, not a JDK." >&2
    echo "       jlink needs a full JDK: brew install openjdk@17" >&2
    exit 1; }
  echo "    JRE: jlink from $JAVA_BIN"
  # jdk.httpserver is REQUIRED and not part of java.se — LanguageTool's
  # local server is built on com.sun.net.httpserver, and without the
  # module it dies at startup with NoClassDefFoundError (verified live in
  # the P20 build session). jdk.unsupported covers sun.misc users in the
  # dependency tree. ~90 MB.
  "$JLINK" --add-modules java.se,jdk.httpserver,jdk.unsupported \
           --strip-debug --no-man-pages --no-header-files --compress=2 \
           --output vendor/jre
  vendor/jre/bin/java -version 2>&1 | head -1 | sed 's/^/    bundled /'
fi

# --- the .app --------------------------------------------------------------
echo "==> building Researchly.app (py2app)"
rm -rf build dist
"$PYTHON" setup.py py2app > /tmp/researchly-py2app.log 2>&1 || {
  echo "error: py2app failed — tail of log:" >&2
  tail -30 /tmp/researchly-py2app.log >&2; exit 1; }

APP="dist/Researchly.app"
RES="$APP/Contents/Resources"
[ -d "$RES" ] || { echo "error: $RES missing after build" >&2; exit 1; }

echo "==> injecting vendor/ into the bundle"
cp -R vendor "$RES/vendor"

# Modifying the bundle invalidates the build's signature; Apple Silicon
# refuses unsigned code entirely, so re-sign ad-hoc.
echo "==> ad-hoc signing"
codesign --force --deep --sign - "$APP" 2>/dev/null || {
  echo "warning: codesign failed — the app may not launch on Apple Silicon" >&2; }

# --- verification (the P18 lesson: test the artifact, not the intent) ------
echo "==> verifying the bundle"
FAIL=0
for path in \
    "Contents/MacOS/Researchly" \
    "Contents/Resources/vendor" ; do
  [ -e "$APP/$path" ] || { echo "    MISSING: $path" >&2; FAIL=1; }
done
if [ "$SKIP_LT" = 0 ]; then
  ls "$RES"/vendor/LanguageTool*/languagetool-server.jar >/dev/null 2>&1 \
    || { echo "    MISSING: bundled LanguageTool jar" >&2; FAIL=1; }
fi
if [ "$SKIP_JRE" = 0 ]; then
  "$RES/vendor/jre/bin/java" -version >/dev/null 2>&1 \
    || { echo "    BROKEN: bundled JRE does not run" >&2; FAIL=1; }
fi
# the engine must FIND the bundle exactly as a Finder launch would
RESOURCEPATH="$RES" "$PYTHON" - << 'PYEOF' || FAIL=1
import sys
sys.path.insert(0, "../../packages/core")
from researchly import health
v = health.vendor_dir()
assert v is not None, "vendor_dir() did not find the injected bundle"
import os
if os.path.isdir(os.path.join(str(v), "jre")):
    assert health.bundled_java(), "bundled_java() missed vendor/jre"
    health.reset_java_cache()
    assert health.find_java() == health.bundled_java(), \
        "find_java() did not prefer the bundled JRE"
print("    engine discovery: OK")
PYEOF
[ "$FAIL" = 0 ] || { echo "error: bundle verification failed" >&2; exit 1; }
du -sh "$APP" | sed 's/^/    size: /'

# --- installers ------------------------------------------------------------
if [ "$MAKE_DMG" = 1 ]; then
  echo "==> building Researchly-$VERSION.dmg"
  rm -f "Researchly-$VERSION.dmg"
  STAGE=$(mktemp -d)
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "Researchly" -srcfolder "$STAGE" -ov \
          -format UDZO "Researchly-$VERSION.dmg" > /dev/null
  rm -rf "$STAGE"
fi

if [ "$MAKE_PKG" = 1 ]; then
  echo "==> building Researchly-$VERSION.pkg"
  rm -f "Researchly-$VERSION.pkg"
  pkgbuild --component "$APP" \
           --install-location /Applications \
           --identifier local.researchly.desktop \
           --version "$VERSION" \
           "Researchly-$VERSION.pkg" > /dev/null
fi

echo
echo "Done."
[ "$MAKE_DMG" = 1 ] && echo "  Researchly-$VERSION.dmg — drag-to-Applications disk image"
[ "$MAKE_PKG" = 1 ] && echo "  Researchly-$VERSION.pkg — double-click installer (installs to /Applications)"
echo
echo "Tester experience: install, launch (first time: right-click → Open,"
echo "because the app is ad-hoc signed), grant Accessibility when prompted."
echo "No Python, no Java, no downloads — the grammar tier works offline."
echo
echo "Distribution note: for sharing beyond personal testers, both"
echo "artifacts need Developer ID signing + notarization (Apple Developer"
echo "Program), then:  codesign --sign 'Developer ID Application: …' and"
echo "xcrun notarytool submit. The build itself does not change."
