# PyInstaller spec for Maze Q — produces a standalone double-clickable app.
#
# Usage (via build_app.sh — preferred):
#   ./build_app.sh
#
# Direct usage (for debugging the spec):
#   pyinstaller --clean --noconfirm mazer.spec
#
# Output:
#   macOS → dist/Maze Q.app   (double-click to run; build_app.sh zips it)
#   Linux → dist/Maze Q/      (run dist/Maze\ Q/Maze\ Q; build_app.sh zips it)
#
# How the native library is found at runtime inside the bundle:
#   The cffi extension (_mazer_cffi.cpython-*.so) has an rpath baked in by
#   _ffi_build.py:
#       macOS: @loader_path/../../native
#       Linux: $ORIGIN/../../native
#   Inside the bundle, PyInstaller places the cffi .so at:
#       _MEIPASS/mazer/_mazer_cffi*.so
#   So @loader_path/../../native resolves to _MEIPASS/native/ — which is
#   exactly where we tell PyInstaller to put libmazer.{dylib,so} via the
#   binaries list below.  No rpath patching is required.

import sys

# ---------------------------------------------------------------------------
# Platform-specific native library
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    _native_lib = ("native/libmazer.dylib", "native")
elif sys.platform.startswith("linux"):
    _native_lib = ("native/libmazer.so", "native")
else:
    raise SystemExit(
        "Unsupported platform — only macOS and Linux are supported by this spec."
    )

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["src/mazer/__main__.py"],
    # src/ on the path so `import mazer` resolves to src/mazer/
    pathex=["src"],
    # Include the Rust shared library; placed at native/ inside the bundle
    # so the existing @loader_path/../../native rpath in the cffi .so works.
    binaries=[_native_lib],
    datas=[],
    # The cffi extension is imported inside a try/except in _ffi.py, so
    # PyInstaller's static analysis may miss it.  Listing it here ensures
    # it is collected.
    hiddenimports=["mazer._mazer_cffi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Maze Q",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX disabled — it can corrupt cffi extensions and signed macOS dylibs.
    upx=False,
    # No terminal window on macOS / Windows.
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Maze Q",
)

# ---------------------------------------------------------------------------
# macOS .app bundle
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Maze Q.app",
        icon=None,
        bundle_identifier="com.jmisabella.mazeq",
        info_plist={
            "CFBundleName": "Maze Q",
            "CFBundleDisplayName": "Maze Q",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
