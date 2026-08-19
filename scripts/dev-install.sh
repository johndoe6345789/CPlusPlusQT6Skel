#!/usr/bin/env bash
# Build from source and install into /Applications. This is the update
# mechanism for a single-machine setup: a full build is ~30s and an
# incremental one a couple of seconds, so there is nothing for an
# auto-updater to do.
#
# No signing is needed. A locally built bundle carries no com.apple.quarantine
# attribute, so Gatekeeper does not gate it -- the ad-hoc signature CMake
# applies is enough. (Distributing to another Mac is what would require a
# Developer ID certificate and notarization; see scripts/release-macos.sh.)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="metabuilder-qt6.app"
DEST="${DEST:-/Applications}"
QT_PREFIX="${QT_PREFIX:-/opt/homebrew/opt/qt}"

# cmake and git are denied access to /Volumes/Install macOS Sequoia by macOS
# privacy protection on that mount, so build from a copy on the internal disk.
# Grant the terminal Full Disk Access (or move the checkout off that volume)
# and BUILD_DIR can simply point back into the source tree.
BUILD_ROOT="${BUILD_ROOT:-$HOME/.cache/metabuilder-build}"

case "$SRC" in
    /Volumes/*)
        echo "==> Source is on $(df -h "$SRC" | awk 'NR==2{print $NF}'); staging to $BUILD_ROOT"
        mkdir -p "$BUILD_ROOT/src"
        rsync -a --delete \
              --exclude 'build-macos' --exclude 'build' --exclude '.git' \
              "$SRC/" "$BUILD_ROOT/src/"
        WORK="$BUILD_ROOT/src"
        ;;
    *)
        WORK="$SRC"
        ;;
esac

echo "==> Configuring"
cmake -S "$WORK" -B "$WORK/build" -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$QT_PREFIX"

echo "==> Building"
cmake --build "$WORK/build"

BUILT="$WORK/build/$APP_NAME"
[ -d "$BUILT" ] || { echo "error: $BUILT not found" >&2; exit 1; }

echo "==> Installing to $DEST"
# Replace rather than merge: rsync --delete stops a stale file from a previous
# build surviving inside the bundle.
pkill -f "$DEST/$APP_NAME" 2>/dev/null || true
mkdir -p "$DEST/$APP_NAME"
rsync -a --delete "$BUILT/" "$DEST/$APP_NAME/"

echo "==> Installed $(du -sh "$DEST/$APP_NAME" | cut -f1) to $DEST/$APP_NAME"
echo "    open \"$DEST/$APP_NAME\""
