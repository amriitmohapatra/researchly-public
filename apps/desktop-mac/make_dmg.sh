#!/bin/bash
# Package dist/Researchly.app into Researchly.dmg (drag-to-Applications).
set -e
cd "$(dirname "$0")"

[ -d "dist/Researchly.app" ] || { echo "Run build_app.sh first."; exit 1; }

STAGING=$(mktemp -d)
cp -R "dist/Researchly.app" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create -volname "Researchly" -srcfolder "$STAGING" \
        -ov -format UDZO "Researchly.dmg"
rm -rf "$STAGING"

echo "Created Researchly.dmg"
