#!/usr/bin/env bash
# =============================================================================
# build_rust.sh — Build the native mazer Rust library for the host machine.
#
# This is step 1 of the project's two-step build. The top-level orchestrator
# `build.sh` calls this script, then invokes `python -m mazer._ffi_build` to
# produce the cffi extension that Python imports. You can also run this
# script standalone if you only want to refresh the Rust artifact.
#
# What this does, end-to-end:
#   1. Verifies the host has a Rust toolchain and a C compiler installed.
#   2. Clones (or pulls) the upstream mazer Rust source into ./mazer/.
#   3. Patches the cloned Cargo.toml so the crate builds as a `cdylib`
#      (a dynamic library Python can dlopen at runtime via cffi).
#   4. Runs `cargo build --release` for the host target.
#   5. Stages the resulting libmazer.{dylib|so} and include/mazer.h into
#      ./native/, which is where the cffi build (step 2) reads them from.
#
# Why no DEVELOP/RELEASE argument (cf. iOS setup.sh):
#   The iOS script needs that flag because the simulator and physical-device
#   builds use *different* Rust targets (aarch64-apple-ios-sim vs
#   aarch64-apple-ios) and ship different binaries. For the Python project
#   there is only one target — the host machine — so a mode flag would be
#   noise. Always builds in release mode by default. Pass `--debug` to opt
#   into a debug build for faster compiles when iterating on the Rust side.
#
# Why we don't run `brew update` / `brew install` / `xcode-select --install`:
#   The iOS script provisions a fresh dev box. This script runs every time a
#   contributor pulls main, so triggering Homebrew updates and Xcode CLT
#   prompts on every run is hostile and slow. Instead we *check* for the
#   tools we need (cargo, a C compiler) and bail with an actionable message
#   if they're missing. Provisioning is the user's responsibility, one time.
#
# Why we don't `rm -rf target/` or `cargo update` by default:
#   - `target/` holds Cargo's incremental compilation cache. Wiping it on
#     every run forces a full rebuild (~30-60s on a clean checkout). Pass
#     `--clean` to force a clean rebuild when you actually need one.
#   - `cargo update` rewrites Cargo.lock with the latest semver-compatible
#     versions of every dependency from crates.io. That introduces churn we
#     can't reproduce later: two contributors running build.sh on the same
#     day can end up with different transitive deps. Cargo.lock is the
#     source of truth for "exactly which versions did we build against,"
#     and `cargo build` honors it. We don't touch it from this script.
#
# Idempotency:
#   Running this script twice in a row is safe and fast. Pass `--clean` to
#   force a from-scratch rebuild of the Rust crate.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
BUILD_PROFILE="release"   # "release" or "debug"
CLEAN_BUILD=0             # 1 = wipe target/ before building

usage() {
    cat <<EOF
Usage: $0 [--debug] [--clean] [--help]

Builds the mazer Rust library as a host-native cdylib and stages the
resulting binary + header into ./native/ for the Python cffi layer.
This is the Rust-only step; run ./build.sh (the top-level orchestrator)
to build both the Rust library and the cffi extension in order.

Options:
  --debug    Build with the dev profile (faster compile, slower runtime).
             Default is --release.
  --clean    Remove mazer/target/ before building. Use when the cache
             might be stale (e.g. after a toolchain upgrade).
  --help     Show this message.
EOF
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug) BUILD_PROFILE="debug"; shift ;;
        --clean) CLEAN_BUILD=1; shift ;;
        --help|-h) usage 0 ;;
        *) echo "Error: unknown argument '$1'" >&2; usage 1 ;;
    esac
done

# -----------------------------------------------------------------------------
# Resolve paths
#
# We want this script to work regardless of where it's invoked from
# (`./build_rust.sh`, `bash build_rust.sh`, `~/proj/build_rust.sh`, or via
# the top-level `./build.sh` orchestrator). Anchor everything to the
# directory the script itself lives in.
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAZER_SRC_DIR="$SCRIPT_DIR/mazer"      # cloned upstream Rust source
NATIVE_DIR="$SCRIPT_DIR/native"        # staged build outputs (gitignored)
MAZER_REPO_URL="https://github.com/jmisabella/mazer.git"

# -----------------------------------------------------------------------------
# Host OS detection
#
# The dynamic library extension differs by OS:
#   macOS  → libmazer.dylib
#   Linux  → libmazer.so
#   Windows → mazer.dll  (NOT supported here — see comment below)
#
# We're only branching on OS *family*, not architecture. cargo will pick the
# right host arch automatically (x86_64 vs aarch64 vs whatever), and the
# resulting filename is identical across archs within the same OS family.
# Supporting Windows would require handling a different filename pattern
# (no `lib` prefix) and the MSVC toolchain's quirks; out of scope for now.
# -----------------------------------------------------------------------------
case "$(uname -s)" in
    Darwin)
        HOST_OS="macos"
        LIB_EXT="dylib"
        ;;
    Linux)
        HOST_OS="linux"
        LIB_EXT="so"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "Error: Windows is not currently supported by build.sh." >&2
        echo "       The cffi binding assumes a libmazer.{dylib,so} layout." >&2
        exit 1
        ;;
    *)
        echo "Error: unrecognized host OS '$(uname -s)'." >&2
        exit 1
        ;;
esac
LIB_NAME="libmazer.$LIB_EXT"
echo "==> Detected host OS: $HOST_OS (expecting $LIB_NAME)"

# -----------------------------------------------------------------------------
# Toolchain checks
#
# We need:
#   - cargo (Rust build tool)         — installed via rustup
#   - a C compiler (cc or clang)      — Rust uses one to link cdylibs
#                                       and some crates' build.rs scripts
#                                       invoke it directly
#
# We *don't* try to install these for the user. Just fail loudly with a
# pointer to the canonical install instructions.
# -----------------------------------------------------------------------------
if ! command -v cargo >/dev/null 2>&1; then
    cat >&2 <<EOF
Error: 'cargo' not found on PATH.

Install Rust via rustup:
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

Then re-open your shell (or 'source ~/.cargo/env') and re-run this script.
EOF
    exit 1
fi

if ! command -v cc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
    cat >&2 <<EOF
Error: no C compiler ('cc' or 'clang') found on PATH.

  macOS: install Xcode Command Line Tools:
           xcode-select --install
  Linux: install your distro's build-essential equivalent, e.g.
           sudo apt install build-essential       # Debian/Ubuntu
           sudo dnf groupinstall 'Development Tools'  # Fedora/RHEL
EOF
    exit 1
fi

echo "==> Toolchain OK: $(cargo --version)"

# -----------------------------------------------------------------------------
# Fetch / refresh the upstream mazer source
#
# Mirrors the iOS script's clone-or-pull pattern. We treat ./mazer/ as a
# tracked checkout of upstream main; running this script always lands on
# the latest commit there.
#
# Validity check: we don't just test `[ -d mazer ]` because an empty
# directory there (e.g. left by earlier scaffolding) would pass that test
# and then `git -C mazer pull` would walk up the directory tree, find the
# *parent* repo's .git, and pull the wrong repo. We require both:
#   - mazer/.git exists (it's a real checkout, not just an empty dir)
#   - its origin URL matches MAZER_REPO_URL (someone didn't clone the
#     wrong thing into this slot)
# If either check fails we discard whatever's there and clone fresh.
# -----------------------------------------------------------------------------
needs_clone=0
if [ ! -d "$MAZER_SRC_DIR/.git" ]; then
    needs_clone=1
else
    existing_origin="$(git -C "$MAZER_SRC_DIR" config --get remote.origin.url 2>/dev/null || true)"
    if [ "$existing_origin" != "$MAZER_REPO_URL" ]; then
        echo "==> $MAZER_SRC_DIR points at unexpected origin '$existing_origin' — re-cloning."
        needs_clone=1
    fi
fi

if [ "$needs_clone" -eq 1 ]; then
    # `git clone` refuses to clone into a non-empty existing directory, so
    # clear it out first. Safe: this path is gitignored and only ever holds
    # the upstream Rust source we're about to re-fetch anyway.
    rm -rf "$MAZER_SRC_DIR"
    echo "==> Cloning $MAZER_REPO_URL into $MAZER_SRC_DIR"
    git clone "$MAZER_REPO_URL" "$MAZER_SRC_DIR"
else
    echo "==> Updating existing checkout at $MAZER_SRC_DIR"
    git -C "$MAZER_SRC_DIR" pull --ff-only origin main
fi

# -----------------------------------------------------------------------------
# Patch Cargo.toml to declare crate-type = ["cdylib"]
#
# Why cdylib (not staticlib):
#   - staticlib produces a .a archive that gets linked at compile time.
#     That's what the iOS app needs because the iOS toolchain links the
#     final binary itself.
#   - cdylib produces a .dylib/.so/.dll that's loaded at *runtime* by the
#     consumer (here: Python's cffi via dlopen). Python can't statically
#     link a .a, so cdylib is the right call for us.
#
# Why we patch upstream's Cargo.toml instead of forking:
#   The upstream crate is consumed by multiple frontends with different
#   needs (iOS wants staticlib, we want cdylib). Patching the local clone
#   on each build keeps us in sync with upstream without maintaining a
#   long-lived fork.
#
# Patching strategy:
#   - If [lib] already exists with crate-type set to cdylib: nothing to do.
#   - If [lib] exists but crate-type is wrong (e.g. staticlib left over
#     from a prior iOS-style build, or missing): rewrite that line.
#   - If [lib] doesn't exist at all: prepend a [lib] block.
#
# We use perl (not GNU sed) because BSD sed (macOS) and GNU sed (Linux)
# disagree on the syntax for in-place editing. Perl behaves identically
# on both.
# -----------------------------------------------------------------------------
CARGO_TOML="$MAZER_SRC_DIR/Cargo.toml"
if [ ! -f "$CARGO_TOML" ]; then
    echo "Error: $CARGO_TOML missing — clone may be corrupt." >&2
    exit 1
fi

echo "==> Ensuring [lib] crate-type = [\"cdylib\"] in Cargo.toml"
if grep -qE '^\[lib\]' "$CARGO_TOML"; then
    if grep -qE '^\s*crate-type\s*=\s*\[\s*"cdylib"\s*\]' "$CARGO_TOML"; then
        echo "    [lib] crate-type already set to cdylib — no change needed."
    elif grep -qE '^[[:space:]]*crate-type[[:space:]]*=' "$CARGO_TOML"; then
        # Replace the existing (wrong) crate-type line. Note: `.*` does not
        # match newlines, and perl's default `$` matches before the line's
        # trailing \n, so this rewrites just the value and leaves the
        # newline structure of the file intact.
        perl -i -pe 's/^[ \t]*crate-type[ \t]*=.*$/crate-type = ["cdylib"]/' "$CARGO_TOML"
        echo "    Rewrote crate-type to cdylib."
    else
        # [lib] exists but no crate-type line under it — insert one
        # *immediately after* the [lib] header. The pattern uses [ \t]*
        # (not \s*) so it only consumes horizontal whitespace at the end
        # of the line, never the trailing newline. Consuming the \n would
        # merge the following line ("name = ...") onto the inserted
        # crate-type line and break the TOML.
        perl -i -pe 's/^(\[lib\])[ \t]*$/$1\ncrate-type = ["cdylib"]/' "$CARGO_TOML"
        echo "    Added crate-type = [\"cdylib\"] under existing [lib]."
    fi
else
    # No [lib] section at all — prepend one.
    {
        echo '[lib]'
        echo 'crate-type = ["cdylib"]'
        echo
        cat "$CARGO_TOML"
    } > "$CARGO_TOML.new"
    mv "$CARGO_TOML.new" "$CARGO_TOML"
    echo "    Prepended new [lib] section."
fi

# -----------------------------------------------------------------------------
# Optional clean
# -----------------------------------------------------------------------------
if [ "$CLEAN_BUILD" -eq 1 ]; then
    echo "==> --clean: removing $MAZER_SRC_DIR/target/"
    rm -rf "$MAZER_SRC_DIR/target"
fi

# -----------------------------------------------------------------------------
# Build
#
# `cargo build` (no --target) builds for the host triple. Cargo writes
# release builds to target/release/ and debug builds to target/debug/.
# -----------------------------------------------------------------------------
echo "==> Building mazer ($BUILD_PROFILE) for host..."
if [ "$BUILD_PROFILE" = "release" ]; then
    (cd "$MAZER_SRC_DIR" && cargo build --release)
    BUILD_OUT_DIR="$MAZER_SRC_DIR/target/release"
else
    (cd "$MAZER_SRC_DIR" && cargo build)
    BUILD_OUT_DIR="$MAZER_SRC_DIR/target/debug"
fi

# -----------------------------------------------------------------------------
# Stage outputs into ./native/
#
# cffi (Stage 2) will be configured with:
#   include_dirs = ["native"]
#   library_dirs = ["native"]
#   libraries    = ["mazer"]
# so everything it needs lives under ./native/ — both the .dylib/.so and
# the mazer.h header.
# -----------------------------------------------------------------------------
mkdir -p "$NATIVE_DIR"

BUILT_LIB="$BUILD_OUT_DIR/$LIB_NAME"
if [ ! -f "$BUILT_LIB" ]; then
    echo "Error: expected build artifact $BUILT_LIB not found." >&2
    echo "       (Did the crate build something other than a cdylib?)" >&2
    exit 1
fi
cp "$BUILT_LIB" "$NATIVE_DIR/$LIB_NAME"
echo "==> Staged $NATIVE_DIR/$LIB_NAME"

# -----------------------------------------------------------------------------
# macOS only: rewrite the dylib's install_name to @rpath/libmazer.dylib.
#
# Why this matters:
#   On macOS, every dylib carries an "install name" (LC_ID_DYLIB) baked in at
#   link time. When something links against the dylib, the linker copies that
#   install name verbatim into the consumer's LC_LOAD_DYLIB entry, and the
#   dynamic loader uses it at runtime to find the dylib.
#
#   Cargo's default install name is the *absolute path* of the build output:
#     /<repo>/mazer/target/release/deps/libmazer.dylib
#   Without intervention, the cffi extension we build in step 2 inherits that
#   absolute path. The rpath we bake into the .so (@loader_path/../../native)
#   becomes dead weight, and the .so breaks the moment that absolute path
#   stops existing — `cargo clean`, moving the repo, or even running on a
#   different machine all cause "image not found" at import time.
#
#   Rewriting the staged copy's install name to @rpath/libmazer.dylib makes
#   the linker propagate THAT into the .so's LC_LOAD_DYLIB. Combined with
#   the .so's rpath (@loader_path/../../native), dyld resolves it as
#       @rpath/libmazer.dylib  →  <so dir>/../../native/libmazer.dylib
#   which is exactly where this script staged it.
#
# Linux: not needed. ELF's DT_NEEDED stores just the soname (e.g.
#   "libmazer.so"), not an absolute path, so the runpath we set on the .so
#   is enough.
# -----------------------------------------------------------------------------
if [ "$HOST_OS" = "macos" ]; then
    install_name_tool -id "@rpath/$LIB_NAME" "$NATIVE_DIR/$LIB_NAME"
    echo "    Set install_name to @rpath/$LIB_NAME"
fi

HEADER_SRC="$MAZER_SRC_DIR/include/mazer.h"
if [ ! -f "$HEADER_SRC" ]; then
    echo "Error: expected $HEADER_SRC not found in upstream checkout." >&2
    exit 1
fi
cp "$HEADER_SRC" "$NATIVE_DIR/mazer.h"
echo "==> Staged $NATIVE_DIR/mazer.h"

echo
echo "Done. Native artifacts ready under $NATIVE_DIR/"
