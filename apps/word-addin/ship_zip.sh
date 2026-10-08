#!/bin/bash
# Assemble the shareable Word add-in tester package.
#
#   bash word-addin/ship_zip.sh          -> shipping/Researchly-WordAddin-<ver>.zip
#
# The previous package was assembled by hand and silently shipped an engine
# three modules out of date (no api.py / config.py / health.py), which is
# exactly the sort of thing a script prevents. This one copies the engine
# from source every time and FAILS if anything essential is missing.

set -e
cd "$(dirname "$0")"
CORE="$(cd ../../packages/core && pwd)"
ADDIN="$(pwd)"
REPO="$(cd ../.. && pwd)"
VERSION="${VERSION:-v0.8}"
PYTHON="${PYTHON:-python3.10}"

STAGE="Researchly-WordAddin-$VERSION"
OUT="$REPO/shipping/$STAGE.zip"
rm -rf "/tmp/$STAGE" && mkdir -p "/tmp/$STAGE" "$REPO/shipping"

# --- engine ---------------------------------------------------------------
mkdir -p "/tmp/$STAGE/researchly"
cp "$CORE"/researchly/*.py "/tmp/$STAGE/researchly/"
cp -R "$CORE"/researchly/data "/tmp/$STAGE/researchly/"

# Everything the surfaces import must actually be present. A missing module
# would only surface as a traceback on a tester's machine.
for mod in api config health engine document metrics telemetry transform \
           spelling lexicons review abstract_lens \
           rules_lexical rules_syntax rules_spelling rules_grammar; do
  [ -f "/tmp/$STAGE/researchly/$mod.py" ] || {
    echo "error: researchly/$mod.py missing from the package" >&2; exit 1; }
done

# --- add-in ---------------------------------------------------------------
mkdir -p "/tmp/$STAGE/word-addin"
cp "$ADDIN"/server.py "$ADDIN"/manifest.xml \
   "$ADDIN"/install-mac.sh "$ADDIN"/README.md \
   "/tmp/$STAGE/word-addin/"
cp -R "$ADDIN"/web "/tmp/$STAGE/word-addin/"
cp "$CORE"/requirements.txt "/tmp/$STAGE/"

cat > "/tmp/$STAGE/start-server.sh" <<'EOF'
#!/bin/bash
# Start the Researchly server, then open the add-in in Word.
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" word-addin/server.py "$@"
EOF
chmod +x "/tmp/$STAGE/start-server.sh" "/tmp/$STAGE/word-addin/install-mac.sh"

cp "$ADDIN/INSTALL-STEP-BY-STEP.md" "/tmp/$STAGE/1-START-HERE.md"
cp "$ADDIN/README-TESTERS.md"       "/tmp/$STAGE/2-ABOUT.md"

# --- verify it runs before shipping it ------------------------------------
if command -v "$PYTHON" >/dev/null 2>&1; then
  "$PYTHON" - <<PYCHK || { echo "error: package failed its smoke test" >&2; exit 1; }
import sys
sys.path.insert(0, "/tmp/$STAGE")
from researchly import api, config, health          # noqa: F401
from researchly.engine import REGISTRY
import researchly.rules_lexical, researchly.rules_syntax    # noqa: F401
import researchly.rules_spelling, researchly.rules_grammar  # noqa: F401
assert len(REGISTRY) >= 30, f"only {len(REGISTRY)} rules registered"
print(f"  smoke test: {len(REGISTRY)} rules registered, engine imports clean")
PYCHK
fi

rm -f "$OUT"
(cd /tmp && zip -rq "$OUT" "$STAGE" -x "*.DS_Store" -x "*__pycache__*")
rm -rf "/tmp/$STAGE"

echo "Created $OUT ($(du -h "$OUT" | cut -f1))"
echo "Testers need Python 3.9+; install-mac.sh fetches deps + the spaCy model."
