"""Build script for the cffi extension that binds the native mazer library.

Run this AFTER ./build_rust.sh has staged ./native/libmazer.{dylib,so} and
./native/mazer.h. The top-level ./build.sh orchestrator does both steps in
order; this module can also be invoked standalone:

    python -m mazer._ffi_build

What it produces:
    src/mazer/_mazer_cffi.cpython-<ver>-<platform>.so

That extension is then importable as `mazer._mazer_cffi`, and the runtime
re-export in `mazer._ffi` does `from mazer._mazer_cffi import ffi, lib`.

Why "API out-of-line" mode (instead of ABI/dlopen mode):
    cffi has two modes:
      - ABI mode: parse the cdef at runtime, ffi.dlopen() the library.
        No C compiler needed at install time, but every type/struct field
        offset is computed by cffi's pure-Python parser. That parser is
        not C, so it can't honor #pragma pack, doesn't know your platform's
        size_t/long width, and silently drifts from the real ABI when the
        header changes shape. Bugs are subtle and corrupt memory.
      - API mode: cffi generates a tiny C shim, compiles it against the
        real header (via #include "mazer.h"), and the C compiler computes
        the struct layout. The result is a Python extension module that
        knows the *actual* ABI of the library it's linked against.
    "Out-of-line" means the shim is built once at build time, not on every
    import. This script is that one-time build.

Why we don't slurp the header into cdef():
    cffi's cdef() parser is a strict subset of C — it understands prototypes,
    typedefs, structs, but NOT preprocessor directives, attributes, or
    anything else. The upstream `mazer.h` also contains duplicate
    declarations of `mazer_get_generation_steps_count` and
    `mazer_get_generation_step_cells` (declared once normally, then again
    inside the same extern "C" block — appears to be an upstream copy/paste).
    cdef() rejects duplicates. So we hand-write the cdef with each
    declaration appearing exactly once, while set_source() pulls in the
    real header for the C compiler.

Why we link with an rpath:
    The compiled `.so` (a Python extension) has to dlopen `libmazer.dylib`
    at import time. Without a runtime search path, the dynamic loader only
    looks in standard system locations (/usr/lib, etc.) and we'd have to
    set DYLD_LIBRARY_PATH/LD_LIBRARY_PATH every time we run Python or copy
    libmazer next to the extension. With `@loader_path/../../native` (macOS)
    or `$ORIGIN/../../native` (Linux) baked into the .so as an rpath, the
    loader resolves libmazer relative to the extension's own location:
        src/mazer/_mazer_cffi*.so
                  └── @loader_path/../../native/libmazer.{dylib,so}
                                  ├── ..   = src/
                                  ├── ..   = repo root
                                  └── native/  = where build_rust.sh stages it
    This works for in-repo development. Wheel distribution (where `native/`
    isn't alongside the installed package) is out of scope here — that
    would need bundling libmazer into the wheel via auditwheel/delocate.

Why we compile in a temp build dir then copy the .so:
    cffi's recompile() emits both the generated `.c` file and the compiled
    `.so` into the same `tmpdir`. We don't want the `.c` cluttering the
    source tree (and if it ever drifted out of sync with the header it
    could confuse readers). Compiling under build/cffi/ keeps generated
    artifacts out of src/mazer/ and copies only the final binary into the
    package directory.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cffi import FFI


# -----------------------------------------------------------------------------
# Path resolution
#
# This file lives at <repo>/src/mazer/_ffi_build.py:
#   parents[0] = src/mazer
#   parents[1] = src
#   parents[2] = <repo root>
# -----------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
NATIVE_DIR = REPO_ROOT / "native"
BUILD_DIR = REPO_ROOT / "build" / "cffi"
EXT_MODULE = "mazer._mazer_cffi"


# -----------------------------------------------------------------------------
# cdef — the declarations cffi needs to know about.
#
# Hand-written, NOT slurped from mazer.h, because:
#   1. cffi's cdef() parser doesn't handle #include / #ifdef / etc.
#   2. The upstream header has duplicate prototypes for two functions; cdef()
#      rejects duplicates.
#
# Field-for-field copy of FFICell from mazer.h — cffi uses these to compute
# Python attribute access; the actual struct layout still comes from the C
# compiler at set_source() time, so a mismatch here would be caught loudly
# (via a verification step cffi runs internally) rather than silently
# corrupting memory.
#
# `void` in `mazer_ffi_integration_test(void)` is intentional. The header
# declares it with empty parens, which in C means "unspecified args" (K&R
# style), not "no args". cffi parses that as a varargs-ish prototype and
# can fail to bind cleanly. `(void)` is the C99 way to say "takes nothing".
# -----------------------------------------------------------------------------
CDEF = r"""
typedef struct Grid Grid;

typedef struct FFICell {
    size_t x;
    size_t y;
    const char* maze_type;
    const char** linked;
    size_t linked_len;
    int32_t distance;
    bool is_start;
    bool is_goal;
    bool is_active;
    bool is_visited;
    bool has_been_visited;
    bool on_solution_path;
    const char* orientation;
    bool is_square;
} FFICell;

Grid*    mazer_generate_maze(const char *request_json);
void     mazer_destroy(Grid *maze);
FFICell* mazer_get_cells(Grid *maze, size_t *length);
void     mazer_free_cells(FFICell *ptr, size_t length);
size_t   mazer_get_generation_steps_count(Grid *grid);
FFICell* mazer_get_generation_step_cells(Grid *grid, size_t step_index, size_t *length);
void*    mazer_make_move(void* grid_ptr, const char* direction);
int      mazer_ffi_integration_test(void);
"""


def _rpath_link_args() -> list[str]:
    """Bake a loader-relative rpath into the extension so it can find libmazer."""
    if sys.platform == "darwin":
        return ["-Wl,-rpath,@loader_path/../../native"]
    if sys.platform.startswith("linux"):
        # `$ORIGIN` is interpreted by ld.so at load time, not by the shell.
        # cffi passes extra_link_args as a list to subprocess.run with no
        # shell, so the literal `$ORIGIN` survives intact through the linker
        # and into the resulting DT_RUNPATH entry.
        return ["-Wl,-rpath,$ORIGIN/../../native"]
    return []


def _fix_macho_load_path(so_path: Path) -> None:
    """Rewrite any libmazer LC_LOAD_DYLIB in the .so to @rpath/libmazer.dylib.

    Belt-and-suspenders for build_rust.sh's install_name fix: even if a stale
    .so was linked against the cargo-baked absolute path of libmazer.dylib,
    this postprocess rewrites it to use the rpath we set at link time. After
    this runs, the resulting LC_LOAD_DYLIB will be `@rpath/libmazer.dylib`,
    which dyld resolves via the .so's rpath to <pkg>/../../native/.

    No-op on Linux (ELF's DT_NEEDED is just a soname; rpath is sufficient).
    No-op if the LC_LOAD_DYLIB is already @rpath-relative.
    """
    if sys.platform != "darwin":
        return

    try:
        out = subprocess.check_output(["otool", "-L", str(so_path)], text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # otool not available (rare on macOS) or refused — skip silently;
        # if the .so is broken we'll find out at import time.
        return

    target = "@rpath/libmazer.dylib"
    for line in out.splitlines():
        # otool -L lines look like: "\t<path> (compatibility version ...)"
        stripped = line.strip()
        if not stripped or "libmazer" not in stripped:
            continue
        # Take the path before the parenthesized version info.
        old = stripped.split(" (compatibility")[0].strip()
        if old == target or old.startswith("@rpath/"):
            continue
        subprocess.check_call(
            ["install_name_tool", "-change", old, target, str(so_path)]
        )
        print(f"    Patched LC_LOAD_DYLIB: {old} → {target}")
        return  # only one libmazer reference per .so


def _build_ffi() -> FFI:
    ffi = FFI()
    ffi.cdef(CDEF)
    ffi.set_source(
        EXT_MODULE,
        '#include "mazer.h"',
        include_dirs=[str(NATIVE_DIR)],
        library_dirs=[str(NATIVE_DIR)],
        libraries=["mazer"],
        extra_link_args=_rpath_link_args(),
    )
    return ffi


def main() -> None:
    if not NATIVE_DIR.is_dir():
        sys.exit(
            f"error: {NATIVE_DIR} does not exist. Run ./build_rust.sh first "
            f"(or ./build.sh to do both steps)."
        )
    if not (NATIVE_DIR / "mazer.h").is_file():
        sys.exit(f"error: {NATIVE_DIR / 'mazer.h'} missing. Re-run ./build_rust.sh.")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ffi = _build_ffi()
    # ffi.compile returns the absolute path of the built extension.
    so_path = Path(ffi.compile(tmpdir=str(BUILD_DIR), verbose=True))

    # Copy the .so into the package directory so it's importable as
    # `mazer._mazer_cffi`. Use copy2 to preserve mtime — handy if anything
    # downstream timestamps against it.
    target = PKG_DIR / so_path.name
    shutil.copy2(so_path, target)
    _fix_macho_load_path(target)
    print(f"==> Installed cffi extension at {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
