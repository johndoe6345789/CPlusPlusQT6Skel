#!/usr/bin/env bash
# Build, sign, notarize and publish a macOS release.
#
# The appcast is published to the metabuilder repo (not this one) because that
# is the public download point; SUFeedURL in Info.plist points at
# .../releases/latest/download/appcast.xml, which always resolves to the newest
# release, so the URL never changes.
#
# Sparkle will refuse an update that is not Developer ID signed and notarized:
# an ad-hoc signature is enough to run locally but Gatekeeper blocks the
# swap-and-relaunch. Set SIGN_IDENTITY to a "Developer ID Application" cert.
#
# Required:
#   SIGN_IDENTITY   e.g. "Developer ID Application: Your Name (TEAMID)"
#   NOTARY_PROFILE  notarytool keychain profile (xcrun notarytool store-credentials)
# The Sparkle EdDSA private key is read from the login keychain by sign_update;
# it is never passed on the command line.
set -euo pipefail

VERSION="${1:?usage: release-macos.sh <version>   e.g. 0.2.0}"
RELEASE_REPO="${RELEASE_REPO:-johndoe6345789/metabuilder}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build-release"
DIST="$ROOT/dist"
APP="$BUILD/metabuilder-qt6.app"

: "${SIGN_IDENTITY:?set SIGN_IDENTITY to a Developer ID Application certificate}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE to a notarytool keychain profile}"

echo "==> Building $VERSION"
cmake -S "$ROOT" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PREFIX_PATH="${QT_PREFIX:-/opt/homebrew/opt/qt}"
cmake --build "$BUILD"

echo "==> Deploying Qt into the bundle"
"${QT_PREFIX:-/opt/homebrew/opt/qt}/bin/macdeployqt" "$APP" \
    -qmldir="$ROOT/qml" -always-overwrite

# Sign inside-out: nested code must be signed before the bundle that contains it.
echo "==> Signing"
find "$APP/Contents/Frameworks" -name "*.framework" -maxdepth 1 -print0 2>/dev/null |
    while IFS= read -r -d '' fw; do
        codesign --force --options runtime --timestamp \
                 --sign "$SIGN_IDENTITY" "$fw"
    done
# Sparkle's helper tools are separate executables and need signing individually.
for helper in "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices/"*.xpc \
              "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/Autoupdate" \
              "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/Updater.app"; do
    [ -e "$helper" ] && codesign --force --options runtime --timestamp \
                                 --sign "$SIGN_IDENTITY" "$helper"
done
codesign --force --options runtime --timestamp --deep \
         --sign "$SIGN_IDENTITY" "$APP"
codesign --verify --strict --verbose=2 "$APP"

echo "==> Notarizing"
mkdir -p "$DIST"
ZIP="$DIST/MetaBuilder-$VERSION.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"   # re-zip so the staple is included

echo "==> Generating signed appcast"
# generate_appcast signs each update with the EdDSA key from the keychain and
# writes appcast.xml alongside the archives in $DIST.
"${SPARKLE_BIN:?set SPARKLE_BIN to the Sparkle bin directory}/generate_appcast" \
    --download-url-prefix "https://github.com/$RELEASE_REPO/releases/download/v$VERSION/" \
    "$DIST"

echo "==> Publishing to $RELEASE_REPO"
gh release create "v$VERSION" "$ZIP" "$DIST/appcast.xml" \
    --repo "$RELEASE_REPO" \
    --title "MetaBuilder $VERSION" \
    --generate-notes

echo "==> Done. Feed: https://github.com/$RELEASE_REPO/releases/latest/download/appcast.xml"
