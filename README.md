# mazer-python

A Python maze game that wraps the mazer Rust library via [cffi](https://cffi.readthedocs.io/) and renders with [pygame-ce](https://pyga.me/).

## Status

Early development — see [`.planning/PLAN.md`](.planning/PLAN.md) for the staged build plan.

## Requirements

- Python 3.11+
- Rust toolchain (for building the native library; see Stage 1)
- macOS or Linux (Windows not yet supported)

## First-time setup

```bash
# Create and activate a virtual environment (use Python 3.11+; 3.13 recommended)
python3.13 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode with dev dependencies
pip install -e '.[dev]'
```

## Build

The project has two build steps that must run in order. The top-level
`build.sh` runs them both:

```bash
./build.sh                # = ./build_rust.sh && python -m mazer._ffi_build
```

What each step does:

1. **`./build_rust.sh`** — clones/pulls the upstream
   [mazer](https://github.com/jmisabella/mazer) Rust crate, patches it to a
   `cdylib`, runs `cargo build --release`, and stages `libmazer.{dylib,so}`
   plus `mazer.h` into `./native/`. Pass `--debug` for a debug build or
   `--clean` to wipe the cargo cache. Run `./build_rust.sh --help` for details.

2. **`python -m mazer._ffi_build`** — compiles the cffi extension that
   binds `libmazer` to the Python `mazer` package. Produces
   `src/mazer/_mazer_cffi.cpython-<ver>-<platform>.so`. Requires the
   artifacts from step 1; bails with an error if `./native/` is empty.

You can run either step standalone (e.g. while iterating on the Python
side, just rerun the cffi step). The orchestrator `./build.sh` exists to
guarantee correct ordering on a fresh checkout. Any args passed to
`./build.sh` are forwarded to `./build_rust.sh`.

## Run

```bash
python -m mazer
```

## Test

```bash
pytest
```

See [`test.sh`](test.sh) for pytest cheatsheet notes; the script runs `pytest -v`.

## Layout

```
mazer-python/
  pyproject.toml         # hatchling build; cffi + pygame-ce + setuptools (build dep)
  build.sh               # top-level orchestrator (Rust then cffi)
  build_rust.sh          # step 1: builds & stages the Rust cdylib
  native/                # gitignored — libmazer.{dylib,so} + mazer.h staged here
  build/cffi/            # gitignored — cffi's intermediate C source + .so
  src/mazer/
    __init__.py
    __main__.py          # python -m mazer entry point
    _ffi_build.py        # step 2: builds the cffi extension
    _ffi.py              # runtime re-export of `ffi` and `lib`
    _mazer_cffi*.so      # gitignored — the compiled cffi extension
    types.py             # MazeRequest, Direction, MazeType, Algorithm
    maze.py              # Pythonic Maze + Cell
    ui/                  # Pygame app + renderer
  tests/
```
