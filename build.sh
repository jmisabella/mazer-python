#!/usr/bin/env bash
# =============================================================================
# build.sh — Top-level build orchestrator.
#
# Builds the project from source in two ordered steps:
#
#   1. ./build_rust.sh
#         Clones / pulls the upstream Rust mazer crate, patches it to a
#         cdylib, builds it, and stages libmazer.{dylib,so} + mazer.h
#         into ./native/.
#
#   2. python -m mazer._ffi_build
#         Compiles the cffi extension (`src/mazer/_mazer_cffi*.so`) which
#         dlopens the libmazer staged in step 1. This is the binding the
#         Python `mazer` package imports at runtime.
#
# Why two scripts and not one:
#   The Rust step is heavy (cargo download/build, only changes when upstream
#   moves) and the cffi step is fast (a handful of seconds). Splitting them
#   means iterating on the Python side doesn't have to re-check the Rust
#   crate, and CI can cache them separately. You can also run either step
#   standalone:
#       ./build_rust.sh                # only the Rust portion
#       .venv/bin/python -m mazer._ffi_build   # only the cffi portion
#   This top-level script is just the convenience wrapper that runs both
#   in the right order — which matters because step 2 needs the artifacts
#   step 1 produces.
#
# Argument forwarding:
#   Any args you pass to build.sh are forwarded verbatim to build_rust.sh.
#   So `./build.sh --debug` runs the Rust step in debug mode, then the
#   cffi step (which has no flags). See `./build_rust.sh --help` for
#   supported flags.
#
# Prerequisite:
#   .venv/ must exist at the repo root with the project installed:
#       python3.13 -m venv .venv
#       source .venv/bin/activate
#       pip install -e '.[dev]'
#   See README.md for the full first-time setup.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"

# -----------------------------------------------------------------------------
# Step 1: build the Rust cdylib
# -----------------------------------------------------------------------------
echo "==> [1/2] Building native Rust library..."
"$SCRIPT_DIR/build_rust.sh" "$@"

# -----------------------------------------------------------------------------
# Step 2: build the cffi extension
#
# We require .venv/bin/python rather than relying on whatever `python` is on
# PATH because:
#   - The cffi build needs the `cffi` package itself, which lives in the
#     venv (editable install of this project pulls it in).
#   - `python -m mazer._ffi_build` needs the `mazer` package importable —
#     also satisfied by the editable install in .venv.
# Falling back to system python would either fail with ImportError or, worse,
# silently use a different Python than the one the user runs `pytest` and
# `python -m mazer` with, producing a mismatched .so suffix.
# -----------------------------------------------------------------------------
if [ ! -x "$VENV_PY" ]; then
    cat >&2 <<EOF

Error: $VENV_PY not found.

The cffi build step needs a virtualenv with this project installed in
editable mode. Create one (one-time setup):

    python3.13 -m venv .venv
    source .venv/bin/activate
    pip install -e '.[dev]'

Then re-run ./build.sh.
EOF
    exit 1
fi

echo
echo "==> [2/2] Building cffi extension..."
"$VENV_PY" -m mazer._ffi_build

echo
echo "Done. Run 'pytest' to verify, or 'python -m mazer' to launch."
