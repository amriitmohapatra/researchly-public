#!/bin/bash
# Assemble the shareable macOS tester package:
#   Researchly-macOS-v0.7.zip  =  Researchly.dmg + tester guide
#
# Run ON YOUR MAC after building:  bash build_app.sh && bash make_dmg.sh
# then:                            bash ship_zip.sh

set -e
cd "$(dirname "$0")"
VERSION="${VERSION:-v0.8}"

if [ ! -f "Researchly.dmg" ]; then
  echo "Researchly.dmg not found in this folder."
  echo "Build it first:  bash build_app.sh && bash make_dmg.sh"
  exit 1
fi

STAGE="Researchly-macOS-$VERSION"
rm -rf "$STAGE" "$STAGE.zip"
mkdir "$STAGE"
cp Researchly.dmg "$STAGE/"
cp INSTALL-STEP-BY-STEP.md "$STAGE/1-START-HERE.md"
cp README-TESTERS-macOS.md "$STAGE/2-ABOUT.md"

zip -rq "$STAGE.zip" "$STAGE" -x "*.DS_Store"
rm -rf "$STAGE"

SIZE=$(du -h "$STAGE.zip" | cut -f1)
echo "Created $STAGE.zip ($SIZE) — share this file with testers."
echo "(Large size is normal: it contains Python + the language model.)"
