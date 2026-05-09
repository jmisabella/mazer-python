#!/usr/bin/env bash
# build_app.sh — build a standalone Maze Q app via PyInstaller.
#
# Prerequisites (all must be satisfied before running):
#   1. ./build.sh has been run — native/libmazer.{dylib,so} and the cffi
#      extension src/mazer/_mazer_cffi*.so must exist.
#   2. pyinstaller >= 6.0 is installed in the active Python environment:
#          pip install -e '.[dev]'   (installs pyinstaller among dev deps)
#
# Output:
#   macOS → dist/Maze Q.app              (double-click to launch)
#            dist/Maze-Q-macos-<arch>.zip (ready to upload to GitHub Releases)
#   Linux → dist/Maze Q/                 (run dist/Maze\ Q/Maze\ Q)
#            dist/Maze-Q-linux-<arch>.zip (ready to upload to GitHub Releases)
#
# GitHub Releases — after a successful build:
#   gh release create v1.0.0 \
#       --title "Maze Q v1.0.0" \
#       --notes "macOS and Linux standalone builds. Download, unzip, and double-click."
#   gh release upload v1.0.0 dist/Maze-Q-macos-arm64.zip   # adjust filename

set -euo pipefail

# ---------------------------------------------------------------------------
# Detect platform
# ---------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Darwin)
        PLATFORM="macos"
        NATIVE_LIB="native/libmazer.dylib"
        APP_DIR="dist/Maze Q.app"
        ;;
    Linux)
        PLATFORM="linux"
        NATIVE_LIB="native/libmazer.so"
        APP_DIR="dist/Maze Q"
        ;;
    *)
        echo "error: unsupported platform '$OS' — only macOS and Linux are supported." >&2
        exit 1
        ;;
esac

ZIP_NAME="Maze-Q-${PLATFORM}-${ARCH}.zip"

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------
if ! command -v pyinstaller &>/dev/null; then
    echo "error: pyinstaller not found in the current Python environment." >&2
    echo "  Run:  pip install -e '.[dev]'  (or pip install 'pyinstaller>=6.0')" >&2
    exit 1
fi

if [ ! -f "$NATIVE_LIB" ]; then
    echo "error: $NATIVE_LIB not found." >&2
    echo "  Run ./build.sh first to build the Rust library and cffi extension." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
echo "==> Building Maze Q standalone app (${PLATFORM}/${ARCH})..."
pyinstaller --clean --noconfirm mazer.spec

# ---------------------------------------------------------------------------
# Zip for distribution
# ---------------------------------------------------------------------------
echo ""
echo "==> Creating dist/$ZIP_NAME ..."
(
    cd dist
    # Remove a stale zip from a previous run so zip doesn't append to it.
    rm -f "$ZIP_NAME"
    if [ "$PLATFORM" = "macos" ]; then
        zip -qr "$ZIP_NAME" "Maze Q.app"
    else
        zip -qr "$ZIP_NAME" "Maze Q"
    fi
)

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo " Build complete: dist/$ZIP_NAME"
echo "================================================================"
echo ""
echo "To test locally:"
if [ "$PLATFORM" = "macos" ]; then
    echo "  open \"dist/Maze Q.app\""
else
    echo "  \"dist/Maze Q/Maze Q\""
fi
echo ""
echo "To publish a GitHub Release:"
echo "  # Create the release (do this once per version):"
echo "  gh release create v1.0.0 \\"
echo "      --title 'Maze Q v1.0.0' \\"
echo "      --notes 'Standalone build — download, unzip, double-click. No Python required.'"
echo ""
echo "  # Upload this build's zip:"
echo "  gh release upload v1.0.0 \"dist/$ZIP_NAME\""
