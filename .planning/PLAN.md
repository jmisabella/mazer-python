## SESSION 0 [uncompleted]
### Prep — Reference materials
- [ ] Create .planning/referenced_resources/iOS_app/
- [ ] Copy setup.sh into it
- [ ] Copy mazer.h into it
- [ ] Copy ffi.rs into it
- [ ] Copy ContentView.swift (and any other UI-relevant Swift files) into it
- [ ] Verify all paths referenced in Sessions 2 and 5 actually exist
- [ ] Add PLAN.md (this file) to the repo root

## SESSION 1 [uncompleted]
### Stage 0 — Repo scaffolding
Create a Python project for a maze game that wraps the existing Rust mazer library via cffi and renders with Pygame. Project layout:

mazer-py/
  pyproject.toml         # uses hatchling or setuptools, declares cffi + pygame
  build.sh               # fetches & builds the Rust lib (next stage)
  native/                # build output: libmazer.{so,dylib} + mazer.h
  src/mazer/
    __init__.py
    _ffi.py              # cffi binding (Stage 2)
    types.py             # MazeRequest, Direction, MazeType, Algorithm enums/dataclasses
    maze.py              # Pythonic Maze, Cell wrappers (Stage 3)
    ui/
      __init__.py
      app.py             # Pygame entry point (Stage 4)
      renderer.py
  tests/
    test_ffi.py
    test_maze.py
    test_integration.py
  .gitignore             # ignores native/, mazer/, __pycache__, .venv, etc.
  README.md

Set up `pyproject.toml` with Python 3.11+, cffi >= 1.16, pygame-ce >= 2.5, pytest >= 8 as dev dep. Add a `python -m mazer` entry point that launches the UI. Don't implement the modules yet — just create the skeleton with `pass` or `NotImplementedError`, plus a working pytest collection that finds the empty test files.

## SESSION 2 [uncompleted]
### Stage 1 — Build script
Write `build.sh` modeled on the referenced iOS `.planning/referenced_resources/iOS_app/setup.sh`, but targeting the host machine for use with Python (not iOS). Differences from the iOS script:

1. Crate type must be `cdylib`, not `staticlib` — Python loads dynamic libraries at runtime via cffi.
2. No `rustup target add` for iOS targets; build for the host (`cargo build --release` with no `--target` flag).
3. After building, copy the resulting `libmazer.dylib` (macOS) or `libmazer.so` (Linux) into `./native/`, and copy `include/mazer.h` into `./native/` as well.
4. Detect host OS to know which extension to look for. Support macOS (arm64 + x86_64) and Linux. Bail with a clear error on Windows for now.
5. Same git clone/pull behavior as the iOS script for the `mazer/` subdirectory. Same `Cargo.toml` patching pattern, but ensuring `cdylib` instead of `staticlib`.

The script should be idempotent: running it twice should update the source and rebuild without errors.

## SESSION 3 [uncompleted]
### Stage 2 — cffi binding
Implement `src/mazer/_ffi.py` using cffi in API-out-of-line mode. Use a hand-written `cdef` string (do not slurp the header — it has duplicate declarations that will break cffi). The cdef should declare exactly:

- The opaque `Grid` type (as `typedef struct Grid Grid;`).
- The `FFICell` struct matching the header field-for-field.
- Each of the 8 functions: `mazer_generate_maze`, `mazer_destroy`, `mazer_get_cells`, `mazer_free_cells`, `mazer_get_generation_steps_count`, `mazer_get_generation_step_cells`, `mazer_make_move`, `mazer_ffi_integration_test`.

Use `ffi.set_source()` with `#include "mazer.h"` and link against mazer from `./native/`. Provide a build helper (`_ffi_build.py`) that compiles the binding once. The runtime module should `from _mazer_cffi import ffi, lib` and re-export them.

In tests/test_ffi.py, write tests that:
1. Assert `lib.mazer_ffi_integration_test() == 42`.
2. Generate a small Orthogonal maze via JSON, assert non-null pointer, destroy it.
3. Get cells from a generated maze, assert length matches width × height for Orthogonal, free them, destroy the grid.
4. Try an invalid direction on `mazer_make_move`, assert it returns NULL.
5. Generate a maze with `capture_steps: true`, assert `mazer_get_generation_steps_count > 0`, fetch step 0's cells, free them.

These tests should be ugly, low-level, and exhaustive — they're the FFI safety net.

## SESSION 4 [uncompleted]
### Stage 3 — Pythonic wrapper
Build the high-level API on top of `_ffi.py`. Every test in this stage should read like a usage example — descriptive names, minimal setup, one concept per test. Tests are documentation.

In `types.py`:
- class `MazeType(str, Enum)`: `ORTHOGONAL`, `DELTA`, `RHOMBIC` with values matching the Rust strings ("Orthogonal" etc).
- `class Algorithm(str, Enum)`: at minimum `WILSONS`, `HUNT_AND_KILL`, `RECURSIVE_BACKTRACKER`, `BINARY_TREE`, `SIDEWINDER`, `ALDOUS_BRODER` — string values matching Rust. Confirm the full list against the Rust source.
- class `Direction(str, Enum)`: `UP`, `DOWN`, `LEFT`, `RIGHT`, `UPPER_LEFT`, `UPPER_RIGHT`, `LOWER_LEFT`, `LOWER_RIGHT` — values "Up", "Down", "UpperLeft", etc.
- `@dataclass(frozen=True) class Coord: x: int, y: int`.
- `@dataclass class MazeRequest`: fields matching the JSON schema, with `to_json() -> str` method.

In `maze.py`:
- `@dataclass(frozen=True) class Cell`: pure-Python copy of FFICell data — `coord`, `linked: frozenset[Direction]`, `distance`, `is_start`, `is_goal`, `is_active`, `is_visited`, `has_been_visited`, `on_solution_path`, `orientation`, `is_square`, `maze_type`. No FFI pointers leak into this class.
- `class Maze`: context manager. `__init__` takes a `MazeRequest`, calls `mazer_generate_maze`, raises `MazeGenerationError` on null. `cells() -> list[Cell]` calls `mazer_get_cells`, copies into Python `Cell` objects, immediately frees the FFI array. Cache the cells list and invalidate the cache on `move()`. `move(direction: Direction) -> bool `calls `mazer_make_move`, returns True on success, False on rejected move (does NOT raise — rejected moves are normal gameplay). `generation_steps() -> Iterator[list[Cell]]` lazily yields each step's cells. `__exit__` calls mazer_destroy. Also implement `__enter__` and a `close()` method, with idempotent destroy (don't double-free).
- `class MazeGenerationError(Exception)`.

In `tests/test_maze.py`, write tests like:
- `test_generate_small_orthogonal_maze` — shows the basic `with Maze(request) as m:` pattern.
- `test_cells_count_matches_dimensions` — for an Orthogonal NxM maze.
- `test_start_cell_marked_correctly` — exactly one cell has `is_start=True` at the requested coords.
- `test_goal_cell_marked_correctly` — likewise for goal.
- `test_initial_active_cell_is_start` — at generation, the active cell should be the start.
- `test_invalid_move_returns_false_and_grid_intact` — try a move into a wall, assert False, assert state unchanged.
- `test_valid_move_advances_active_cell` — find a direction in `start.linked`, move, assert active cell changed.
- `test_solution_path_connects_start_to_goal` — filter cells by `on_solution_path`, assert connected chain from start to goal.
- `test_distances_form_valid_heatmap` — start cell distance is 0, goal distance > 0, no negative distances on reachable cells.
- `test_capture_steps_yields_progressive_cells` — with `capture_steps=True`, step count > 0, last step has same cell count as final maze.
- `test_context_manager_destroys_on_exit` — use a weakref or counter to verify cleanup.

Use the actual `_ffi` module — no mocking. These are integration tests against real Rust.

## SESSION 5 [uncompleted]
### Stage 4 — Pygame UI
Orthogonal mazes only for this stage. Build the Pygame app in `src/mazer/ui/`. Match the look and feel of the iOS app which has been copied to `.planning/referenced_resources/iOS_app/`.

`renderer.py`:
- `class Renderer`: takes a Pygame surface and cell size. `draw(cells: list[Cell], show_heatmap: bool, show_solution: bool)`.
- For each cell, draw walls on edges whose direction is not in `cell.linked`.
- Heatmap: map `distance` to a color gradient (interpolate between two colors by `distance / max_distance`). Match the iOS palette.
- Solution path: when toggled, highlight cells where `on_solution_path` is True with a subtle fill.
- The active cell (player): draw a distinct marker.
- Start cell: marker A; goal cell: marker B.

`app.py`:
- Game loop: arrow keys → `Direction.UP/DOWN/LEFT/RIGHT` → `maze.move(...)`. Ignore moves that return False.
- `H` toggles heatmap. `S` toggles solution path. `R` regenerates with the same parameters. `N` opens a new-maze dialog (or just reads from a config for now — keep it simple).
- On reaching the goal cell (`maze.cells()` has a cell where `is_active and is_goal`), show a "Solved!" overlay.
- Window title shows current algorithm and dimensions.

Acceptance: `python -m mazer` launches a window, generates a default maze, you can play it, toggle heatmap, see the solution.

## SESSION 6 [uncompleted]
### Stage 5 — Integration test
In `tests/test_integration.py`:
- `test_solve_maze_by_following_solution_path`: generate a maze, walk the active cell along the `on_solution_path` cells from start to goal, asserting each move succeeds and the final cell is the goal. This exercises the full FFI → wrapper → game-logic stack without touching Pygame.
- `test_multiple_algorithms_all_produce_valid_mazes`: parametrize over every algorithm, generate a small maze with each, assert it's solvable (start has at least one linked direction; goal is reachable via solution path).


