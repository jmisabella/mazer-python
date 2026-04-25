# mazer-python

A Python maze game that wraps the mazer Rust library via [cffi](https://cffi.readthedocs.io/) and renders with [pygame-ce](https://pyga.me/).

## Status

Early development — see [`.planning/PLAN.md`](.planning/PLAN.md) for the staged build plan.

## Requirements

- Python 3.11+
- Rust toolchain (for building the native library; see Stage 1)
- macOS or Linux (Windows not yet supported)

## Setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode with dev dependencies
pip install -e '.[dev]'

# Build the native mazer library (Stage 1 — not yet implemented)
./build.sh
```

## Run

```bash
python -m mazer
```

## Test

```bash
pytest
```

## Layout

```
mazer-python/
  pyproject.toml         # hatchling build, declares cffi + pygame-ce
  build.sh               # fetches & builds the Rust mazer cdylib
  native/                # build output: libmazer.{dylib,so} + mazer.h
  src/mazer/
    __init__.py
    __main__.py          # python -m mazer entry point
    _ffi.py              # cffi binding
    types.py             # MazeRequest, Direction, MazeType, Algorithm
    maze.py              # Pythonic Maze + Cell
    ui/                  # Pygame app + renderer
  tests/
```
