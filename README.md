# mazer-python

A fully-featured maze game written in Python that wraps **mazer** — a maze engine written in Rust — via [cffi](https://cffi.readthedocs.io/), rendered with [pygame-ce](https://pyga.me/). The same Rust library powers both this desktop game and a native [iOS app](#portability-the-same-rust-engine-everywhere), demonstrating that a single, well-designed C FFI surface can serve radically different platforms without modification.

---

## Table of Contents

- [What this is](#what-this-is)
- [Portability: the same Rust engine, everywhere](#portability-the-same-rust-engine-everywhere)
- [Maze types](#maze-types)
- [Algorithms](#algorithms)
- [Features](#features)
- [Requirements](#requirements)
- [First-time setup](#first-time-setup)
- [Build](#build)
- [Run](#run)
- [Controls](#controls)
- [CLI options](#cli-options)
- [In-game menu](#in-game-menu)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Tests](#tests)
- [How the FFI binding works](#how-the-ffi-binding-works)
- [Known limitations](#known-limitations)

---

## What this is

mazer-python is a playable maze game with five distinct grid geometries, thirteen generation algorithms, rich visual overlays, and smooth mouse/keyboard navigation. It was built in 19 focused sessions, each adding a concrete layer — from the raw Rust build pipeline through the cffi binding, the Pythonic wrapper, the Pygame UI, multi-grid rendering, drag-to-move, animated generation playback, and a polished dark-mode settings menu.

The game supports:

- **5 maze grid types**: Orthogonal (squares), Sigma (hexagons), Delta (triangles), Rhombic (rotated diamonds), Upsilon (octagons + squares)
- **13 generation algorithms**: from Wilson's unbiased walk to Recursive Backtracker to Eller's row-by-row algorithm
- **Interactive overlays**: distance heatmap, solution path with cell-by-cell reveal animation, fuchsia trail gradient behind the player
- **Multiple input modes**: arrow keys (with diagonal chord support), maze-specific letter keys, click-to-move, and drag-to-move
- **Animated generation**: watch the maze build cell by cell at 15ms/step; skip with Space
- **In-game settings menu**: change maze type, algorithm, and dimensions without restarting; includes educational descriptions for every type and algorithm

---

## Portability: the same Rust engine, everywhere

The `mazer` Rust crate exposes its maze logic through a stable **C FFI** (`mazer.h`). Because C ABI is universal, the same compiled library ships on three completely different platforms with zero changes to the maze engine itself:

| Platform | Language | Binding |
|----------|----------|---------|
| **iOS** (native app) | Swift | `mazer.xcframework` static library via `import mazer` |
| **Python desktop** (this project) | Python | `cffi` dynamic library (`libmazer.dylib` / `libmazer.so`) |
| **Android** *(planned)* | Kotlin/JVM | JNI dynamic library |

The iOS app and this Python game share the same Rust source. The same `mazer_generate_maze`, `mazer_make_move`, `mazer_get_cells`, and `mazer_get_generation_step_cells` functions drive both. Platform-specific work is limited to the binding glue and the UI layer — the maze logic, pathfinding, distance maps, and generation animation data are identical.

This architecture lets a single engineer maintain one correct maze engine and ship it everywhere, rather than re-implementing (and re-debugging) maze generation in Swift, Python, and Kotlin separately.

---

## Maze types

| Type | Shape | Directions |
|------|-------|-----------|
| **Orthogonal** | Square grid | Up, Down, Left, Right (+ diagonal chords via Rust fallback) |
| **Sigma** | Flat-top hexagonal (odd-q vertical offset) | Up, Down, UpperLeft, UpperRight, LowerLeft, LowerRight |
| **Delta** | Alternating up/down triangles | UpperLeft, UpperRight, Down (Normal) / Up, LowerLeft, LowerRight (Inverted) |
| **Rhombic** | 45°-rotated diamond grid (checkerboard; every other cell exists) | UpperRight, LowerRight, LowerLeft, UpperLeft |
| **Upsilon** | Alternating octagons and squares | Octagons: all 8 directions; Squares: Up, Down, Left, Right |

Each type has a dedicated renderer that was ported field-for-field from the iOS reference app's SwiftUI views.

---

## Algorithms

All 13 algorithms the Rust library supports are exposed. Not every algorithm is compatible with every maze type — the in-game menu filters the list automatically based on the selected grid type.

| Algorithm | Character |
|-----------|-----------|
| **Wilson's** | Unbiased (loop-erased random walk); slow but produces perfect mazes |
| **Aldous-Broder** | Unbiased random walk; very slow on large grids |
| **Recursive Backtracker** | DFS; long winding corridors, high difficulty |
| **Hunt and Kill** | DFS variant; similar to Recursive Backtracker |
| **Binary Tree** | Fast; strong NE diagonal bias (Orthogonal only) |
| **Sidewinder** | Row-based; horizontal bias (Orthogonal only) |
| **Eller's** | Row-by-row; memory-efficient; unique texture |
| **Kruskal's** | Randomly adds edges; uniform texture |
| **Prim's** | Grows outward from a seed; branchy |
| **Growing Tree (Newest)** | Aggressive DFS; long passages |
| **Growing Tree (Random)** | Prim's-like; mixed passage lengths |
| **Recursive Division** | Subdivides regions; strong rectangular rooms |
| **Reverse Delete** | Removes edges from a complete graph; slow |

---

## Features

### Navigation
- **Arrow keys** — move in cardinal directions
- **Diagonal arrow chords** — hold two arrows simultaneously (e.g. `↑` + `→`) for diagonal movement; the Rust resolves fallback directions automatically for maze types that don't support all diagonals
- **Sigma / Delta / Upsilon letter keys** — `W` (Up), `X` (Down), `Q` (UpperLeft), `E` (UpperRight), `Z` (LowerLeft), `C` (LowerRight)
- **Rhombic letter keys** — `Q` (UpperLeft), `E` (UpperRight), `Z` (LowerLeft), `C` (LowerRight)
- **Click-to-move** — click any cell adjacent to the active cell to move there
- **Drag-to-move** — click and drag across the grid; the player follows your cursor through open walls continuously

### Overlays and visuals
- **`H`** — toggle distance heatmap (cells colored by distance from start)
- **`S`** — toggle solution path; on first press, reveals the path cell-by-cell (15ms per cell); pressing again hides it instantly
- **Fuchsia trail** — the 3 cells most recently visited glow progressively lighter shades of pink; the current cell has the lightest tint
- **Open-exit indicators** — small white dots on the active cell show which directions have open walls at a glance
- **Start / Goal markers** — labeled **A** and **B** on the grid
- **Solved! overlay** — appears when you reach the goal cell
- **Random gradient backgrounds** — each maze generates with a unique two-color pastel gradient (ported from the iOS color palette); regenerating picks a new one

### Generation animation
- **`G`** — toggle animation mode (shown in HUD as `anim:on`)
- When animation mode is on, pressing `R` or generating from the menu plays the maze being built cell by cell at 15ms per step
- **Space / Enter / click** — skip animation and jump to the final playable maze
- **Esc** (during animation) — cancel and return to the previous maze
- **`--animate`** CLI flag — start with animation on first launch
- Animation is capped at 16×16 cells per side to keep Aldous-Broder and other slow algorithms from running too long

### Settings menu
- **`M`** — open the dark-mode settings panel
- Change maze type, algorithm, width, and height without restarting
- Each maze type and algorithm displays an educational description panel
- Algorithm list is filtered to only show options compatible with the selected maze type
- Incompatible combinations show an inline error (the Rust validates and returns NULL; the menu surfaces it gracefully)
- Width and height are clamped to what fits on your screen

---

## Requirements

- Python 3.11+
- Rust toolchain (`cargo` in `$PATH`) — only needed to build the native library
- macOS or Linux (Windows not yet supported)
- A C compiler (Clang on macOS, GCC on Linux) — for building the cffi extension

---

## First-time setup

```bash
# Clone the repo
git clone https://github.com/jmisabella/mazer-python
cd mazer-python

# Create and activate a virtual environment (Python 3.11+ required; 3.13 recommended)
python3.13 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode with dev dependencies
pip install -e '.[dev]'
```

---

## Build

The project has two build steps that must run in order. The top-level `build.sh` runs both:

```bash
./build.sh
```

What each step does:

**Step 1 — `./build_rust.sh`**

Clones or updates the upstream [mazer](https://github.com/jmisabella/mazer) Rust crate, patches its `Cargo.toml` to emit a `cdylib`, builds with `cargo build --release`, and stages the results:

```
native/libmazer.dylib   (macOS)
native/libmazer.so      (Linux)
native/mazer.h
```

On macOS it also fixes the dylib's install name to `@rpath/libmazer.dylib` so the library is relocatable.

Optional flags:
```bash
./build_rust.sh --debug    # debug build instead of release
./build_rust.sh --clean    # wipe cargo cache before building
./build_rust.sh --help     # show all options
```

**Step 2 — `python -m mazer._ffi_build`**

Compiles the cffi extension that binds `libmazer` to the Python package, producing:

```
src/mazer/_mazer_cffi.cpython-<ver>-<platform>.so
```

Requires the artifacts from Step 1. Any flags passed to `./build.sh` are forwarded to Step 1:

```bash
./build.sh --debug    # debug Rust build + cffi compile
./build.sh --clean    # clean Rust build + cffi compile
```

You can re-run Step 2 alone while iterating on the Python side:

```bash
python -m mazer._ffi_build
```

---

## Run

```bash
# Default: 20×20 Orthogonal maze, Recursive Backtracker
python -m mazer

# Hexagonal maze
python -m mazer --type sigma

# Triangular maze, custom size
python -m mazer --type delta --width 15 --height 12

# Rhombic maze with a specific algorithm
python -m mazer --type rhombic --algo Wilsons

# Launch with generation animation enabled
python -m mazer --animate

# All options
python -m mazer --help
```

---

## Controls

### Universal (all maze types)

| Key / Action | Effect |
|---|---|
| `H` | Toggle distance heatmap |
| `S` | Toggle solution path (animates on first reveal) |
| `G` | Toggle generation animation mode |
| `R` | Regenerate maze (animates if `G` is on) |
| `M` | Open settings menu |
| `Esc` | Quit (or cancel animation / close menu) |
| Arrow keys | Move (cardinal directions) |
| Two arrows held | Diagonal move (chord) |
| Left-click | Move to adjacent cell |
| Click + drag | Continuous movement through open walls |
| `Space` / `Enter` | Skip generation animation (or regenerate when solved) |

### Orthogonal

Arrow keys cover all four directions. Diagonal chords (e.g. `↑`+`→`) let the Rust engine resolve the closest open cardinal direction.

### Sigma / Delta / Upsilon

| Key | Direction |
|-----|-----------|
| `W` or `↑` | Up |
| `X` or `↓` | Down |
| `Q` | Upper-left |
| `E` | Upper-right |
| `Z` | Lower-left |
| `C` | Lower-right |

### Rhombic

| Key | Direction |
|-----|-----------|
| `Q` | Upper-left |
| `E` | Upper-right |
| `Z` | Lower-left |
| `C` | Lower-right |

Arrow chords (e.g. `↑`+`→` → Upper-right) work on all maze types.

---

## CLI options

```
python -m mazer [OPTIONS]

Options:
  --type {orthogonal,sigma,delta,rhombic,upsilon}
                        Maze grid type (default: orthogonal)
  --width INT           Grid width in cells
  --height INT          Grid height in cells
  --algo ALGORITHM      Generation algorithm (e.g. RecursiveBacktracker,
                        Wilsons, AldousBroder — see Algorithm enum in types.py
                        for the full list)
  --animate             Enable generation animation on first launch
```

Width and height are clamped to what fits on your display. In animation mode, both dimensions are also capped at 16.

---

## In-game menu

Press `M` to open the settings panel. The dark-mode overlay lets you:

- **Cycle maze type** with `←` / `→` or click the `‹ ›` arrows
- **Cycle algorithm** — list is filtered to only show algorithms compatible with the current maze type
- **Edit width and height** — clamped to screen bounds and (when animation mode is on) to the animation cell limit
- **Generate** — applies the new settings immediately; incompatible combinations show an inline error without crashing
- **Esc** — cancel and return to the current maze unchanged

Each maze type and algorithm shows a short educational description directly in the menu panel, adapted from the iOS app's copy.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   mazer (Rust crate)                │
│  Maze generation · pathfinding · step capture       │
│  Exposed via stable C FFI (mazer.h)                 │
└─────────────────┬───────────────────────────────────┘
                  │  libmazer.dylib / libmazer.so
                  │
┌─────────────────▼───────────────────────────────────┐
│              src/mazer/_ffi.py                      │
│  cffi out-of-line binding — ffi + lib               │
│  Hand-written cdef (header has duplicate decls)     │
│  rpath wired to ./native/ for relocatability        │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│         src/mazer/maze.py  +  types.py              │
│  Pythonic API: Maze context manager, Cell dataclass │
│  MazeType, Algorithm, Direction, MazeRequest enums  │
│  No FFI pointers escape; all arrays freed inline    │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│              src/mazer/ui/                          │
│  app.py     — game loop, input, animation state     │
│  renderer.py — 5 renderers + factory dispatch       │
│  menu.py    — dark-mode settings panel              │
└─────────────────────────────────────────────────────┘
```

### Key design decisions

**cffi out-of-line mode** — the binding is compiled once at build time to a `.so`, not interpreted at import time. The `cdef` is hand-written because the upstream header has duplicate prototypes that cffi rejects.

**No FFI pointers leak into Python** — `Maze.cells()` copies every `FFICell` into a frozen Python `Cell` dataclass and frees the Rust-owned array before returning. Callers can hold `Cell` objects indefinitely without risking use-after-free.

**Rust `make_move` fallback chain** — the Rust engine implements a per-direction fallback for every maze type (e.g. `UpperRight` → tries `UpperRight`, then `Up`, then `Right`). This means the Python layer never needs to know which directions a given maze type "really" supports — it sends whatever direction the input resolves to and lets the Rust do the right thing. Diagonal arrow chords on orthogonal, for instance, work transparently without any Python-side special-casing.

**Renderer factory** — `make_renderer(maze_type, surface, cell_size, offset)` returns the correct renderer for the maze type. All five renderers expose the same duck-typed interface (`draw(cells, show_heatmap, show_solution)`, `maze_rect(cells)`, `cell_at(pos, cells)`), so the game loop never branches on maze type after initial dispatch.

**Sigma boundary-clamp handling** — the Rust `assign_neighbors_sigma` clamps diagonal neighbors at boundary rows, causing two direction names to resolve to the same coordinate. Both the renderer and the click/drag handlers resolve walls geometrically (coord-pair linkage sets) rather than trusting direction names at the boundary. This is documented in the Session 7 notes in `.planning/PLAN.md` and is the kind of subtlety that only empirical probing finds.

---

## Project layout

```
mazer-python/
├── pyproject.toml         # hatchling build; cffi + pygame-ce runtime deps
├── build.sh               # orchestrator: Rust build → cffi compile
├── build_rust.sh          # step 1: clone/patch/build Rust cdylib into native/
├── native/                # gitignored — libmazer.{dylib,so} + mazer.h
├── build/cffi/            # gitignored — cffi intermediate C source
├── src/
│   └── mazer/
│       ├── __init__.py
│       ├── __main__.py        # `python -m mazer` entry point
│       ├── _ffi_build.py      # step 2: compile cffi extension
│       ├── _ffi.py            # runtime re-export of ffi + lib
│       ├── _mazer_cffi*.so    # gitignored — compiled cffi extension
│       ├── types.py           # MazeRequest, Direction, MazeType, Algorithm
│       ├── maze.py            # Maze context manager + Cell dataclass
│       └── ui/
│           ├── app.py         # game loop, input handling, animation state
│           ├── renderer.py    # OrthogonalRenderer, SigmaRenderer,
│           │                  # DeltaRenderer, RhombicRenderer, UpsilonRenderer
│           │                  # + make_renderer factory
│           └── menu.py        # dark-mode settings panel (MenuState, draw_menu)
├── tests/
│   ├── test_ffi.py            # low-level FFI safety tests
│   ├── test_maze.py           # Pythonic wrapper unit tests
│   ├── test_integration.py    # full-stack solver tests (all 5 maze types)
│   └── test_ui.py             # renderer smoke, input, menu, animation tests
└── .planning/
    └── PLAN.md                # detailed session-by-session build log
```

---

## Tests

```bash
# Run the full test suite
pytest

# Verbose output
pytest -v

# Run a specific file
pytest tests/test_integration.py -v
```

The suite has **125 tests** across four files, running in ~0.5s. They cover:

- Raw FFI round-trips (generate, get cells, make move, destroy, step capture)
- Pythonic wrapper contracts (context manager lifecycle, move semantics, generation steps, error handling)
- Full-stack solver paths for all five maze types (walk from start to goal by following `on_solution_path`, using actual `maze.move()` calls against real Rust)
- All 13 algorithms on Orthogonal via parametrized tests
- All five renderers under `SDL_VIDEODRIVER=dummy`
- Chord resolver matrix (14 input combinations)
- Click and drag hit-testing for all maze types
- `AnimationState` tick, skip, and multi-step advance
- `MenuState` navigation, value clamping, algorithm filtering, type switching, and error feedback

Tests use real FFI calls against the compiled `libmazer` — no mocking of the Rust layer.

---

## How the FFI binding works

The Rust crate is built as a `cdylib` (shared library). Its public surface is a set of C functions declared in `native/mazer.h`:

```c
// Generate a maze from a JSON request string
Grid *mazer_generate_maze(const char *json_request);

// Destroy a maze (always call this to free Rust memory)
void mazer_destroy(Grid *grid);

// Get all cells as a C array; caller must call mazer_free_cells
FFICell *mazer_get_cells(const Grid *grid, uintptr_t *out_len);
void     mazer_free_cells(FFICell *cells, uintptr_t len);

// Make a move; returns updated Grid* on success, NULL on invalid move
Grid *mazer_make_move(Grid *grid, const char *direction);

// Generation step capture
uintptr_t mazer_get_generation_steps_count(const Grid *grid);
FFICell  *mazer_get_generation_step_cells(const Grid *grid,
              uintptr_t step, uintptr_t *out_len);

// Sanity check
int mazer_ffi_integration_test(void);
```

`src/mazer/_ffi_build.py` compiles this into a cffi extension with `ffi.set_source()`, linking against `native/libmazer.{dylib,so}`. The rpath is baked into the extension so it finds the library relative to itself at runtime (`@loader_path/../../native` on macOS, `$ORIGIN/../../native` on Linux), making the whole thing relocatable.

At runtime, `src/mazer/_ffi.py` does:

```python
from mazer._mazer_cffi import ffi, lib
```

And `maze.py` calls `lib.mazer_generate_maze(...)` etc. through that handle.

---

## Known limitations

- **Windows not supported** — `build_rust.sh` detects the OS and bails on Windows; the cffi rpath logic is also POSIX-only
- **Wheel distribution not implemented** — the `native/` library must be present alongside the package; there is no bundling step for distributing a self-contained wheel
- **Interactive testing requires a display** — renderer visual output and chord keyboard behavior require a real display; test coverage for those paths uses `SDL_VIDEODRIVER=dummy` and pure-function unit tests as a substitute
- **Upsilon and Delta `--type` aliases** are lowercase on the CLI but `MazeType` values match Rust's capitalized strings internally; the CLI lowercases and capitalizes automatically
