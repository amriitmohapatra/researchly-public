#!/bin/bash
# Sideload the Researchly add-in into Word for Mac.
# Copies a manifest into Word's add-in folder ("wef"). Run once; after
# that the add-in appears in Word under Insert > Add-ins (or the Add-ins
# button) > "Developer Add-ins" / "My Add-ins" > Researchly.
#
#   bash install-mac.sh          # the local add-in (server.py on this Mac)
#   bash install-mac.sh hosted   # the hosted add-in (S3): researchly-chi.vercel.app/word
#
# Both can be installed at once: they have different Ids.

set -e
WEF="$HOME/Library/Containers/com.microsoft.Word/Data/Documents/wef"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$WEF"

if [ "${1:-}" = "hosted" ]; then
  cp "$HERE/manifest.hosted.xml" "$WEF/researchly-hosted-manifest.xml"
  echo "Hosted manifest installed to:"
  echo "  $WEF/researchly-hosted-manifest.xml"
  echo
  echo "Next steps:"
  echo "  1. Quit Word completely (Cmd-Q), then reopen it."
  echo "  2. Open a document: Home tab > Researchly (or Insert > Add-ins >"
  echo "     Developer Add-ins / My Add-ins > Researchly)."
  echo "  3. Optional, for 'This computer' mode: python3 \"$HERE/server.py\""
  exit 0
fi

cp "$HERE/manifest.xml" "$WEF/researchly-manifest.xml"

echo "Manifest installed to:"
echo "  $WEF/researchly-manifest.xml"
echo
echo "Next steps:"
echo "  1. Start the local server:   python3 \"$HERE/server.py\""
echo "  2. Quit and reopen Word."
echo "  3. In Word: Insert tab > Add-ins dropdown > Developer Add-ins > Researchly"
echo "     (on some versions: Insert > My Add-ins > Researchly)"
