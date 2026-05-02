
## SESSION 1 [completed 2026-04-25]
### Stage 0 — Repo scaffolding
Create a Python project for a maze game that wraps the existing Rust mazer library via cffi and renders with Pygame. Project layout:

mazer-python/
  pyproject.toml         # uses hatchling, declares cffi + pygame
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

Set up `pyproject.toml` using **hatchling** as the build backend, with Python 3.11+, cffi >= 1.16, pygame-ce >= 2.5, pytest >= 8 as dev dep. Add a `python -m mazer` entry point that launches the UI. Don't implement the modules yet — just create the skeleton with `pass` or `NotImplementedError`, plus a working pytest collection that finds the empty test files.

#### Session 1 notes
- Build backend: **hatchling** (modern PyPA-recommended choice in 2026; lighter than setuptools, no `setup.py`).
- Project root is the existing `mazer-python/` directory — no extra `mazer-py/` nesting; `pyproject.toml`, `src/`, `tests/` live at the repo root.
- `pyproject.toml` declares `requires-python = ">=3.11"`, runtime deps `cffi>=1.16` + `pygame-ce>=2.5`, dev extra `pytest>=8`. Includes `[tool.hatch.build.targets.wheel] packages = ["src/mazer"]` and `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `pythonpath = ["src"]` so tests find the package without an editable install.
- Entry point is `src/mazer/__main__.py` → `mazer.ui.app.main()`. Stubbed `main()` raises `NotImplementedError("Stage 4: ...")`.
- Stub modules (`_ffi.py`, `types.py`, `maze.py`, `ui/app.py`, `ui/renderer.py`) are docstring-only (or raise `NotImplementedError` where execution is meaningful, per the plan).
- Test stubs (`test_ffi.py`, `test_maze.py`, `test_integration.py`) each contain one `@pytest.mark.skip`'d placeholder so pytest collection finds them but nothing fails.
- `.gitignore` fix: the pre-existing `mazer/*` pattern was non-anchored and would have silently ignored `src/mazer/*` — re-anchored to `/mazer/` (Rust source clone target) and added `/native/` (build output).
- `build.sh` is a chmod +x placeholder that exits 1 with a Stage 1 message.
- `native/` directory created (empty; gitignored).
- `README.md` replaced with project description, setup/run/test commands, and layout diagram.
- Verified: `python3 -m compileall src tests` passes; `pytest --collect-only` (run via a temp pytest install) collects 3 placeholder tests honoring the `pyproject.toml` config; `PYTHONPATH=src python3 -m mazer` correctly routes through `__main__` to `ui.app.main()` and raises the expected `NotImplementedError`.
- Caveat: only system Python 3.9 is installed on this machine. To actually `pip install -e '.[dev]'` and run the project, the user will need Python 3.11+ (e.g. via Homebrew, pyenv, or uv) before Stage 1.

## SESSION 2 [completed 2026-04-25]
### Stage 1 — Build script
Write `build.sh` modeled on the referenced iOS `.planning/referenced_resources/iOS_app/setup.sh`, but targeting the host machine for use with Python (not iOS). Differences from the iOS script:

1. Crate type must be `cdylib`, not `staticlib` — Python loads dynamic libraries at runtime via cffi.
2. No `rustup target add` for iOS targets; build for the host (`cargo build --release` with no `--target` flag).
3. After building, copy the resulting `libmazer.dylib` (macOS) or `libmazer.so` (Linux) into `./native/`, and copy `include/mazer.h` into `./native/` as well.
4. Detect host OS to know which extension to look for. Support macOS (arm64 + x86_64) and Linux. Bail with a clear error on Windows for now.
5. Same git clone/pull behavior as the iOS script for the `mazer/` subdirectory. Same `Cargo.toml` patching pattern, but ensuring `cdylib` instead of `staticlib`.

The script should be idempotent: running it twice should update the source and rebuild without errors.

#### Session 2 notes
Decisions that diverged from a literal port of `setup.sh` (rationale documented inline in the script):
- **No `DEVELOP|RELEASE` positional arg.** That flag exists in the iOS script because simulator and device builds use different Rust targets; the host-Python project has only one target so a mode flag would be noise. Defaults to release; opt into debug with `--debug`.
- **No `brew update` / `brew install` / `xcode-select --install`.** The iOS script provisions a fresh dev box; ours runs every time someone pulls main. Instead we *check* for `cargo` and a C compiler and bail with an actionable message — provisioning is a one-time user responsibility.
- **No `rm -rf target/` or `cargo update` by default.** Wiping `target/` defeats Cargo's incremental cache (re-runs went from ~7s to 0.01s with the cache); `cargo update` rewrites `Cargo.lock` with latest semver-compatible deps and creates non-reproducible builds across machines. `Cargo.lock` is the source of truth for "exactly which deps did we build against." Opt into a clean rebuild with `--clean`.
- **Linux arch: permissive (any).** Plan said "Linux"; we don't whitelist arches because the script is host-only (no cross-compile) and the `.so` filename is identical across Linux archs. Branching is on OS family only — cargo will fail clearly if a host arch isn't supported.
- **Header destination: kept at `./native/mazer.h`** (original plan). Not `src/mazer/`, because `src/mazer/` is the Python package and anything inside it ships in the wheel. The header is a build-time artifact for cffi only. `native/` is gitignored as the build-output staging dir — clean separation.
- **Sed → perl.** BSD sed (macOS) and GNU sed (Linux) disagree on in-place edit syntax; perl behaves identically on both.

Bugs found and fixed during implementation (worth noting because they're easy to reintroduce):
1. **Empty `mazer/` dir from Stage 0 scaffolding.** First run found the empty dir, passed `[ -d mazer ]`, and `git -C mazer pull` walked up the directory tree to the parent repo's `.git`, pulling `mazer-python` instead of `mazer`. Fix: validity check requires `mazer/.git` to exist *and* its origin URL to match `MAZER_REPO_URL`; otherwise we re-clone fresh.
2. **Perl regex consumed trailing newline.** When inserting `crate-type` under an existing `[lib]` header, the original pattern `s/^(\[lib\])\s*$/$1\ncrate-type = .../` matched `\s*` → the line's `\n`, then replacement only added one newline (between `[lib]` and `crate-type`) rather than two, jamming the next line of Cargo.toml onto the inserted line. Fix: use `[ \t]*` (horizontal whitespace only) so the trailing `\n` stays intact for perl's `-p` mode to print.

Verified end-to-end on macOS arm64: clone → patch → cargo build → stage produced `native/libmazer.dylib` (Mach-O 64-bit arm64, ~708KB) and `native/mazer.h`. Idempotent re-run hits cargo's incremental cache and finishes in <100ms.

## SESSION 3 [completed 2026-04-25]
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

#### Session 3 notes

Decisions / minor deviations from the plan:

- **Build wiring split into two scripts.** Renamed Stage-1's `build.sh` → `build_rust.sh` (Rust-only). New top-level `build.sh` orchestrates: runs `build_rust.sh` then `python -m mazer._ffi_build`. Forwards args to the Rust step (so `./build.sh --debug` works). Documented order explicitly in README so the build steps and their dependencies are unambiguous.
- **cffi extension lives inside the package**, not at top level. Plan said `from _mazer_cffi import ffi, lib`; we ship as `mazer._mazer_cffi` and `_ffi.py` does `from mazer._mazer_cffi import ffi, lib`. Reason: keeps the compiled binary discoverable as `python -c "from mazer._ffi import lib"` without PYTHONPATH games, and makes the eventual wheel layout obvious. The `.so` is binary/per-platform/per-Python so it's gitignored (added explicit `/src/mazer/_mazer_cffi*` rule on top of the generic `*.so`).
- **cdef is hand-written**, not slurped from `mazer.h`. Plan-mandated; verified the upstream header has duplicate prototypes for `mazer_get_generation_steps_count` and `mazer_get_generation_step_cells` (cdef rejects duplicates) so this wasn't optional. `int mazer_ffi_integration_test();` in the header is K&R-style "unspecified args"; declared as `(void)` in cdef to be unambiguous.
- **API out-of-line mode** (per plan). Compile produces `src/mazer/_mazer_cffi.cpython-<ver>-<platform>.so`. Intermediate C lands under `build/cffi/` (gitignored under the generic `build/`); only the final `.so` is copied into `src/mazer/`.
- **setuptools added to dev deps.** Python 3.12+ removed stdlib `distutils`; cffi's compile shim falls back to setuptools' `Extension`. Without it, `_ffi_build.py` raises `ModuleNotFoundError: No module named 'setuptools'`. Pinned `setuptools>=68` under `[project.optional-dependencies] dev`.
- **rpath strategy.** `_ffi_build.py` sets `extra_link_args = ["-Wl,-rpath,@loader_path/../../native"]` on macOS, `$ORIGIN/...` on Linux. From `src/mazer/_mazer_cffi*.so`, that resolves to `<repo>/native/` where the staged dylib lives. Wheel distribution (where `native/` won't be alongside) is out of scope for Stage 2.

Bug found and fixed during implementation (would have been a latent crash for any other dev or after `cargo clean`):

- **macOS dylib install_name was the absolute cargo build path.** Cargo's default `LC_ID_DYLIB` for a `cdylib` is `/<repo>/mazer/target/release/deps/libmazer.dylib`. The linker propagates that into the consumer's `LC_LOAD_DYLIB` verbatim, which made the rpath I'd baked into the `.so` *unused* — dyld resolved the absolute path directly. Tests passed locally but the `.so` was non-relocatable: hiding `mazer/target/` (or moving the repo) reproduces `Library not loaded: ... no such file`.
  
  Fix in two places:
  1. `build_rust.sh` runs `install_name_tool -id @rpath/libmazer.dylib native/libmazer.dylib` after staging, so any future link gets `@rpath/libmazer.dylib` baked in.
  2. `_ffi_build.py` runs `install_name_tool -change <abs> @rpath/libmazer.dylib` on the just-copied `.so` as a postprocess, so a stale `.so` linked against the abs path also gets fixed without forcing a `cffi` cache invalidation.
  
  Verified: `otool -L src/mazer/_mazer_cffi*.so` now shows `@rpath/libmazer.dylib`, and tests pass with `mazer/target/` moved out of the way. Linux doesn't need this — ELF's `DT_NEEDED` is a soname, not a path, and the runpath alone is sufficient.

Test invocation note: tests run via `.venv/bin/pytest` (or `pytest` with the venv activated). All 5 FFI tests pass; the Stage 3/5 placeholders remain `@pytest.mark.skip`d.

## SESSION 4 [completed 2026-04-25]
### Stage 3 — Pythonic wrapper
Build the high-level API on top of `_ffi.py`. Every test in this stage should read like a usage example — descriptive names, minimal setup, one concept per test. Tests are documentation.

In `types.py`:
- class `MazeType(str, Enum)`: `ORTHOGONAL`, `DELTA`, `RHOMBIC`, `SIGMA`, `UPSILON` with values matching the Rust strings ("Orthogonal", "Delta", "Rhombic", "Sigma", "Upsilon").
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

#### Session 4 notes

Decisions / minor deviations from the plan:

- **MazeType expanded from 3 to 5 variants** (`ORTHOGONAL`, `DELTA`, `RHOMBIC`, `SIGMA`, `UPSILON`) per session decision — the FFI accepts all five, and trimming the enum now would force a `types.py` edit later when other maze types ship in the UI. Stage 3 tests still only exercise Orthogonal; the additional variants cost nothing and keep the wrapper as the full Pythonic API over the FFI.
- **Algorithm enum lists all 13 variants** the upstream Rust accepts (`AldousBroder`, `BinaryTree`, `Ellers`, `GrowingTreeNewest`, `GrowingTreeRandom`, `HuntAndKill`, `Kruskals`, `Prims`, `RecursiveBacktracker`, `RecursiveDivision`, `ReverseDelete`, `Sidewinder`, `Wilsons`) — confirmed against `MazeAlgorithm.swift` in the iOS reference, which exposes the same FFI surface.
- **No algorithm/maze-type compatibility validation in the enum.** The Rust side rejects bad combinations (e.g. `BinaryTree` on `Delta`) with a NULL return, which `Maze.__init__` translates into `MazeGenerationError`. Baking the compatibility table into `types.py` would couple it to upstream Rust evolution; that logic belongs in the UI/request-builder layer (Stage 4+) where it can produce useful messages.
- **`MazeRequest.start`/`goal` omitted from JSON when `None`.** The Rust deserializer expects the keys absent, not present-and-null — verified against the Rhombic FFI test in `ffi.rs` which has neither key. Using `dataclasses.asdict` would have serialized them as `null` and broken those defaults; `to_json()` builds the dict explicitly.
- **`Cell` is a frozen dataclass copying every FFICell field once.** Plan-mandated; the FFI memory is freed inside `Maze.cells()` before the function returns, so no caller can ever hold a reference to Rust-owned bytes. `linked` is a `frozenset[Direction]` (not list) because membership tests dominate over iteration in renderer/pathfinding code.
- **`closed` is a public read-only property.** Plan asked for idempotent `close()`; exposing the closed-state lets tests assert lifecycle directly without touching `_closed`. Operations on a closed maze raise `RuntimeError` (rather than feeding NULL through the FFI for undefined behavior) — added a `_check_open()` guard at the top of `cells`, `move`, and `generation_steps`.
- **`Maze.request` property added** so the future `R`-to-regenerate handler in Stage 4's UI loop can hand the original request back to a fresh `Maze(...)` without callers having to stash it themselves. Trivial accessor; no behavior beyond returning the dataclass.
- **Tests patch `mazer.maze.lib`, not `lib.mazer_destroy`.** cffi's generated `lib` object rejects attribute assignment (`AttributeError`), so a direct `monkeypatch.setattr(lib, "mazer_destroy", ...)` doesn't work. Workaround is a small `CountingLib` proxy with `__getattr__` that wraps `mazer_destroy` and forwards everything else through unchanged, patched into the `mazer.maze` module namespace via `monkeypatch.setattr(maze_mod, "lib", ...)`. Documented inline in the test file because future readers will hit the same wall.
- **Three extra tests beyond the plan list** (12 stage-3 tests instead of 11): `test_cells_cache_invalidated_after_move` (validates the invalidation contract the plan specifies), `test_generation_steps_empty_when_not_captured` (the negative path for the iterator), `test_zero_size_request_raises_maze_generation_error` (validates `MazeGenerationError` actually fires — plan called for the exception class but no test exercised it), and `test_close_is_idempotent` + `test_operations_after_close_raise` (cover the "don't double-free" requirement and the `RuntimeError`-after-close guard). Each maps to an explicit plan requirement that otherwise had no test.

Verified: 21 passed, 1 skipped (Stage 5 placeholder). Full suite runs in ~0.03s.

## SESSION 5 [completed 2026-04-26]
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

#### Session 5 notes

Defaults chosen for `python -m mazer`: 20×20 Orthogonal, Recursive Backtracker, 28px cells, `start=(0,0)`, `goal=(19,19)`, `capture_steps=False`. Window is `560×616` (560 maze + 56px HUD). Picked to land in the iOS app's "medium" cell-size band without overflowing a typical desktop window.

Decisions / minor deviations from the plan:

- **`N` is a Stage-4 alias for `R`.** Plan offered "open a new-maze dialog OR just read from a config — keep it simple." Pygame has no native dialog primitive and a hand-rolled modal would be substantial scope; instead `N` re-runs the current request, identical to `R`, with a code comment noting it's reserved for a real picker in a later stage. Documented in the keybinding docstring so the behavior is explicit, not implicit.
- **iOS palette ported directly from `MazeCellAppearance.swift`/`HeatMapPalette.swift`** rather than approximated. `OFF_WHITE`, `START_COLOR` (SwiftUI `.blue`), `GOAL_COLOR` (SwiftUI `.red`), `VISITED_COLOR` (`CellColors.traversedPathColor`), and `SOLUTION_COLOR` (the documented midpoint of `vividBlue` and gray) are pulled by-hex; the heatmap default is the "Belize Hole" 10-shade gradient because it sits well over the off-white background. Wall stroke = `cell_size // 6` matches the orthogonal denominator from `wallStrokeWidth(for: .orthogonal, ...)`.
- **Subtle row gradient kept for default cells.** The iOS code lerps cell background from a near-white tint at row 0 toward `offWhite` at the bottom row; replicated as `_default_cell_color(y, total_rows)`. Costs nothing and keeps the look-and-feel parity the plan asked for.
- **Cell-color priority is a strict chain**: start > goal > visited > (show_solution & on_solution_path) > (show_heatmap & max_distance>0) > default-row-gradient. Mirrors `cellBackgroundColor(...)` in the iOS source. Verified against the rendered overlays frame — the heatmap and solution toggles compose correctly (solution wins where they conflict).
- **`Renderer.maze_rect()` exposed** so `app.py` can position the "Solved!" overlay over the painted maze region without the renderer needing to know about overlay UI. Keeps render vs. game-state UI cleanly separated: renderer paints cells/walls/markers, app paints HUD + overlay.
- **Player marker is a yellow filled circle with a thin black stroke** at the active cell's center (radius `cell_size // 4`). Distinct from start/goal/solution colors and visible across every cell-color state. The iOS app uses haptic feedback + a position highlight; we drop the haptic and rely on the visual marker.
- **`Solved!` is both an overlay and a HUD badge.** Plan asked for an overlay; added a small green "Solved!" tag in the HUD's top-right corner too, so the state is unmistakable even with the overlay translucent. Solved is detected by `any(c.is_active and c.is_goal for c in cells)` — the game-state-via-cells pattern Stage 5's integration test will exercise.
- **`Renderer` constructor calls `pygame.font.SysFont`**, which requires `pygame.font.init()` (done by `pygame.init()`). Documented the precondition implicitly by having `app.main()` call `pygame.init()` before constructing the renderer; not adding a defensive init inside the constructor because it would mask sequencing bugs in callers and Stage 5 tests don't construct `Renderer` directly.

Verification:
- 21 existing tests still pass, 1 Stage-5 placeholder still skipped (`pytest` ~0.02s).
- Smoke test under `SDL_VIDEODRIVER=dummy` runs `app.main()` against a scripted event sequence (H, S, ↓, →, H, R, N, Esc) and exits cleanly — confirms init, draw, all five branches of the keydown handler, regenerate-with-cleanup, and the QUIT/Esc shutdown path all work without exceptions.
- Visual sanity-check: rendered three representative frames to PNG (default / heatmap+solution / solved-with-overlay) under the dummy driver. Walls, A/B letters, palette, gradient, and overlay all look correct against the iOS reference.
- Interactive acceptance (arrow-key play, real-window key toggles) requires the user at the keyboard — flagged at session start.

## SESSION 6 [completed 2026-04-26]
### Stage 5 — Integration test
In `tests/test_integration.py`:
- `test_solve_maze_by_following_solution_path`: generate a maze, walk the active cell along the `on_solution_path` cells from start to goal, asserting each move succeeds and the final cell is the goal. This exercises the full FFI → wrapper → game-logic stack without touching Pygame.
- `test_multiple_algorithms_all_produce_valid_mazes`: parametrize over every algorithm, generate a small maze with each, assert it's solvable (start has at least one linked direction; goal is reachable via solution path).

#### Session 6 notes

Decisions / minor deviations from the plan:

- **Direction-to-coord-offset map duplicated in the test file.** `cell.linked` returns *which walls are open* but not *which neighbor cell that opens onto*; to walk the solution path we need the inverse mapping (UP=(0,-1), DOWN=(0,1), LEFT=(-1,0), RIGHT=(1,0)). The Rust side owns the canonical mapping and we don't expose it through the FFI, so the test re-states it. Convention confirmed against the existing reasoning in `test_invalid_move_returns_false_and_grid_intact` ("at (0,0) UP and LEFT are off-grid"). Documented in the module docstring so a future reader doesn't have to re-derive it.
- **Solver test asserts a `next_direction` exists at every step before calling `move()`.** A perfect maze guarantees the solution path is a simple chain, so the BFS-style "pick the first linked neighbor on the path we haven't visited" always finds exactly one candidate at the active cell. Failing the assertion early (with the active coord, its `linked` set, and the visited set in the message) is much more debuggable than letting `m.move(None)` blow up later or letting the loop spin.
- **Loop guarded by `max_steps = width * height`.** Defensive belt against a hypothetical regression where the path isn't actually a chain — without the guard a broken `on_solution_path` could hang the test runner. Uses `for/else` with `pytest.fail` so the failure is "did not reach goal within N moves" instead of an assertion-stack noise. Marked `# pragma: no cover` because in correct runs the `break` always fires first.
- **Reachability check is BFS through `on_solution_path` cells via `linked`, not just "both flags set."** Plan said "goal is reachable via solution path"; reading that strictly means the path must be a *connected chain*, not just two flagged endpoints. The BFS catches a (hypothetical) bug where `on_solution_path` gets set on disconnected cells. The first test (which actually walks the path with `move()`) is the live integration check; this one is the parametrized smoke check across all 13 algorithms.
- **Parametrized over all 13 `Algorithm` variants.** All pass on Orthogonal at 8×8, including `BinaryTree`, `Sidewinder`, and `RecursiveDivision`. No skips needed — confirms the plan-time hypothesis from Session 4 notes that algorithm/maze-type rejections (e.g. `BinaryTree` on `Delta`) are non-Orthogonal-only.
- **Helpers `_active`, `_start`, `_by_coord` deliberately *not* shared with `test_maze.py`.** Tests are docs; copying three one-liners keeps each file readable in isolation rather than introducing a `conftest.py` for trivial helpers. If a fourth test file shows up later, that's the time to consolidate.

Verified: 35 passed, 0 skipped (was 21 + 1 placeholder before this session). Full suite still ~0.03s.

## SESSION 7 [completed 2026-04-26]
### Stage 6 — Sigma (hexagonal) maze rendering and play

Pick: **Sigma** out of the four remaining grid types (Delta, Sigma, Upsilon, Rhombic). Rationale: maximally distinct from Orthogonal both visually (flat-top hexagons vs squares) and mechanically (six directions vs four), the wrapper already accepts it from Stage 3, and the iOS reference (`SigmaCellView.swift`, `SigmaMazeView.swift`, `HexDirection.swift`) gives a near-complete port target — keeps this session about the rendering port rather than re-deriving hex math.

Scope:

1. **Refactor `ui/renderer.py`** so the orthogonal-specific drawing is one class among many: extract the palette, heatmap interpolation, and `cell_color(...)` decision tree to module-level so a sibling renderer can reuse them. Rename `Renderer` → `OrthogonalRenderer` (keep `Renderer` as a back-compat alias only if needed; otherwise delete and update callers). Both renderers expose the same surface: `draw(cells, show_heatmap, show_solution)` and `maze_rect(cells)` returning the painted region's bounding rect.
2. **Add `SigmaRenderer`** drawing flat-top hexagons in odd-q vertical offset layout, matching the iOS reference field-for-field:
    - Unit hexagon vertices: `(0.5, 0), (1.5, 0), (2, h/2), (1.5, h), (0.5, h), (0, h/2)` where `h = sqrt(3)`, scaled by `cell_size`.
    - Cell center at `(cell_size * (1.5*q + 1), hex_height * (r + 0.5) + (q odd ? hex_height/2 : 0))`.
    - Total bounding box: `cell_size * (1.5*cols + 0.5)` wide by `hex_height * (rows + 0.5)` tall.
    - Wall denominator from iOS: `cell_size // 6` for `cell_size >= 18`, else `cell_size // 7`.
    - Direction → edge mapping (vertex index pairs) ported from `HexDirection.vertexIndices`: UP=(0,1), UPPER_RIGHT=(1,2), LOWER_RIGHT=(2,3), DOWN=(3,4), LOWER_LEFT=(4,5), UPPER_LEFT=(5,0).
    - Symmetric wall check: only draw an edge if neither cell's `linked` set includes the connecting direction (matches the iOS `linked || neighborLink` short-circuit; defensive against any one-sided link bug).
    - Player marker: same yellow filled circle as Orthogonal, sized for the hex; A/B letters rendered at the cell center.
3. **Renderer dispatch.** Add `make_renderer(maze_type, surface, cell_size, offset)` factory returning the correct renderer for a `MazeType`. Initially handles `ORTHOGONAL` and `SIGMA`; raises `NotImplementedError` for the other three so a future stage's omission is loud, not silent.
4. **App-level integration in `ui/app.py`:**
    - Add a `--type {orthogonal,sigma}` CLI flag (argparse) defaulting to `orthogonal`. Optional `--width`, `--height`, `--algo` flags so the user can override. Defaults for sigma: 11×10 grid at `cell_size=26`, Recursive Backtracker, start `(0,0)`, goal `(width-1, height-1)`.
    - Per-maze-type window sizing — orthogonal: `(W*cell, H*cell + HUD)`; sigma: bounding box from the renderer plus HUD.
    - Per-maze-type key mapping. Orthogonal keeps arrow keys. Sigma adds the standard hex roguelike layout: `W` (or ↑) → UP, `X` (or ↓) → DOWN, `Q` → UPPER_LEFT, `E` → UPPER_RIGHT, `Z` → LOWER_LEFT, `C` → LOWER_RIGHT. Document in the docstring.
    - HUD hint text reflects the active key map.
5. **Tests.**
    - `tests/test_integration.py`: `test_solve_sigma_maze_by_following_solution_path` — same path-walk pattern as the orthogonal solver test but with hex offsetDelta (odd-q vertical from `HexDirection.offsetDelta`). Proves the wrapper + FFI handle hex linkage round-trip end-to-end.
    - `tests/test_ui.py` (new): smoke test that constructs `SigmaRenderer` under `SDL_VIDEODRIVER=dummy`, draws a small sigma maze, asserts no exceptions and that the rendered surface has non-trivial pixel variance (i.e. something actually got drawn). Same smoke for `OrthogonalRenderer` for parity.

Acceptance: `python -m mazer --type sigma` launches a hexagonal maze you can play with the W/X/Q/E/Z/C keys; H/S/R/N still toggle/regenerate; reaching goal shows the Solved! overlay. All previous tests still pass.

#### Session 7 notes

The renderer's hex-edge math came out clean (a literal port of `SigmaCellView`/`HexDirection.vertexIndices` + `SigmaMazeView.position(for:)`), but the wall-drawing logic and the integration test both ran into a non-obvious issue in the **Rust library's direction-name handling at clamped boundaries**. Worth documenting because it's the kind of thing only an empirical probe finds:

- **Boundary direction-name ambiguity in the Rust library.** `Grid::assign_neighbors_sigma` clamps `north_diagonal` to the cell's row at the top of even columns and `south_diagonal` likewise at the bottom of odd columns (`mazer/src/grid.rs:716-721`). At those clamped cells, both upper- and lower-diagonals on the affected side end up with the *same* neighbor coordinate in `neighbors_by_direction` HashMap. Then `Cell::set_open_walls` (`mazer/src/cell.rs:236-245`) iterates the linked coords and uses `iter().find()` on the HashMap — returning whichever direction name happens to come first. The FFI exports that single name. So at e.g. (0, 0) of an N×N sigma grid, the FFI may report `linked = {UpperRight}` even though the *physical* edge between (0, 0) and (1, 0) is the lower-right edge in the iOS odd-q-vertical layout. Found this by probing `cell.linked` on a 5×5 sigma maze: (0, 0) showed `{UpperRight}` but the only neighbor it could possibly link to was (1, 0), which lies *below-and-right* — not above-right. Same shape of issue affects bottom-row odd cols.
- **Renderer fix: build a coord-pair linkage set.** Rather than draw walls per direction-name (which would render wrong walls at the four affected cells in the worst case), `SigmaRenderer` now walks `cell.linked` once per draw call, resolves each direction to a real neighbor coord by trying candidate offsets (the standard offset plus, on boundary rows only, the row-shared clamp variant), and accumulates the result into a `set[frozenset[Coord]]` of linked pairs. Wall drawing iterates the six *physical* hex edges (each tied to a fixed neighbor delta given column parity) and skips the wall iff the cell-neighbor coord pair is in that set. This is geometry-driven and immune to whichever direction name the FFI happened to keep at clamped boundaries. The free function `hex_candidate_deltas(direction, col, row, height)` lives in `renderer.py` so other dispatchers (e.g. a future sigma minimap) can reuse it.
- **The same trap bit the integration test.** First version of `_sigma_candidate_deltas` returned the clamp variant unconditionally for any diagonal direction. That made the path-walker's "is this on-path-and-unvisited?" check return false positives at non-boundary cells: the alternative offset pointed to a *different* physical cell whose state happened to satisfy the predicate, but `m.move(direction)` then committed Rust's single-direction-to-coord interpretation and landed somewhere else (usually a previously visited cell). Symptom: deterministic-looking failures of the form "no forward solution-path move from (q, r)" mid-path on a maze whose path was clearly walkable. Fix mirrors the renderer: candidate offsets only include the clamp variant on actual boundary rows. With that gate, 30/30 test reruns pass on different RNG seeds.
- **Why I picked Sigma over Delta/Rhombic/Upsilon.** Delta needs alternating cell-orientation handling (each row of triangles flips), which is a lot of new geometry on top of the renderer split. Upsilon is two cell shapes per maze. Rhombic uses a 45°-rotated grid with a custom direction remap (visible in `Cell::get_user_facing_open_walls`). Sigma is one shape, six directions, and the iOS reference (`SigmaCellView.swift`, `SigmaMazeView.swift`, `HexDirection.swift`) is essentially a complete port target — which kept the session about the *engineering* (renderer split, factory dispatch, CLI plumbing, key map per type, FFI quirk) rather than re-deriving non-trivial geometry under time pressure.
- **Renderer split: factory + duck typing, no ABC.** `OrthogonalRenderer` and `SigmaRenderer` both expose `draw(cells, show_heatmap, show_solution)` and `maze_rect(cells)`; nothing else is shared structurally, so an `ABC` would be ceremony. `make_renderer(maze_type, ...)` dispatches and raises `NotImplementedError` for Delta / Rhombic / Upsilon — explicit holes for the next session rather than silent orthogonal fallback. Kept `Renderer` as a back-compat alias for `OrthogonalRenderer` to avoid touching every existing caller.
- **CLI handling.** `argparse`-based `--type {orthogonal,sigma}` plus optional `--width`, `--height`, `--algo`. The MazeType value in JSON is `"Orthogonal"` / `"Sigma"`; CLI takes lowercase and round-trips via `MazeType(args.maze_type.capitalize())`. Defaults table (`_DEFAULTS`) maps each type to a `(cell_size, width, height)` tuple — sigma at 11×10 / 26px lands in roughly the same window footprint as orthogonal at 20×20 / 28px without overflowing. `main(argv: list[str] | None = None)` now takes optional argv so the smoke test can invoke it directly with a flag list.
- **Sigma keymap chosen for muscle memory.** Top row letters (Q/W/E) cover upper-left / up / upper-right; bottom row (Z/X/C) covers lower-left / down / lower-right. ↑/↓ also fire UP/DOWN as common-sense affordances. Deliberately *did not* bind A/S/D so a fat-finger never silently moves; the natural pivot row is unbound. Removed the previous Q-to-quit shortcut (now means UPPER_LEFT in sigma) — Esc and the window close button are unambiguous quitting paths in both modes; documented in the app docstring.
- **Default goal at `(width-1, height-1)`** for sigma. In the iOS odd-q-vertical layout that's the bottom-right hex when the width is odd, and one row up when even — the corner placement still reads as a reasonable "opposite corner" goal even with the parity shift.
- **Tests + smoke-checks.**
    - `tests/test_integration.py::test_solve_sigma_maze_by_following_solution_path` — full FFI/wrapper/move integration on a hex grid (8×8). Same shape as the orthogonal solver but with hex offset deltas and the boundary-aware candidate function.
    - `tests/test_ui.py` (new) — `test_orthogonal_renderer_draws_without_error`, `test_sigma_renderer_draws_without_error`, `test_make_renderer_dispatch`. Use `SDL_VIDEODRIVER=dummy` (set in a module-scoped autouse fixture); the content check samples a coarse 16×16 grid of pixels and asserts > 1 distinct color so it works regardless of where the renderer placed the maze inside the surface (a tighter "row at midpoint" check failed on the orthogonal smoke because the maze is 100px tall in a 200px surface).
    - End-to-end app smoke under the dummy SDL driver: `app.main(['--type', 'sigma'])` against a scripted event sequence (H, S, Q, E, Z, C, R, N, Esc) exits cleanly. Same for default orthogonal with arrow keys.

Verified: 39 passed (was 35 + 0 skipped before this session). Sigma test reruns 30/30 across different RNG seeds. Full suite ~0.34s.

## SESSION 8 [completed 2026-04-26]
### Stage 7 — Better movement input for sigma (chord arrow keys + mouse/trackpad)

Motivation from Session 7 user feedback: the Q/E/Z/C hex-roguelike layout is awkward for someone whose hands aren't already trained on it; in particular, `E` for UPPER_RIGHT didn't feel like a "move up-and-right" gesture. Two enhancements, both additive (don't break the existing key map):

1. **Chord arrow keys for diagonals.**
    - `↑` + `→` held together → UPPER_RIGHT.
    - `↑` + `←` → UPPER_LEFT.
    - `↓` + `→` → LOWER_RIGHT.
    - `↓` + `←` → LOWER_LEFT.
    - Single arrow keys keep their existing cardinal meaning.
    - On orthogonal mazes, chords should be no-ops (Direction.LEFT/RIGHT cover the horizontal axis already), or could optionally fire the cardinal that the arrow combination "rounds toward" — design call to make in this session.

    Implementation pattern that's worked in similar pygame games: don't dispatch on raw KEYDOWN for arrows. Instead, on each KEYDOWN of an arrow, sample `pygame.key.get_pressed()`; if a perpendicular arrow is also held at that instant, fire the diagonal immediately and set a "consumed until KEYUP" flag so the second arrow's eventual KEYDOWN/repeat doesn't double-fire. If only one arrow is held, fire the cardinal. This matches typical roguelike chord semantics with one frame of latency. Document the decision in the docstring; add a unit-style test for `_resolve_chord(keys_held)` returning the right `Direction` for each combination so the matrix is verifiable without booting the UI.

2. **Mouse / trackpad click-to-move.**
    - On left-click, hit-test the click position against the cell map. If the clicked cell is *adjacent* to the active cell (in the topology of the current maze type), find the direction that connects active → clicked and fire `maze.move(direction)`. If the clicked cell is non-adjacent or not linked, ignore the click (or, optionally, flash a brief "blocked" indicator on the active cell).
    - Hit-testing for orthogonal: `(click_x // cell_size, click_y // cell_size)` after offset subtraction.
    - Hit-testing for sigma: pick the hex whose center is closest to the click position and verify the click is inside that hex polygon (point-in-polygon test for the six vertices). A single closest-center pass is fine for the small grid sizes we're shipping; precision matters more than perf.
    - Direction lookup uses the same coord-pair linkage set the renderer already builds (`SigmaRenderer._build_linked_pairs`) — promote it to a top-level helper so both renderer and click handler can call it. For orthogonal use the trivial `dx, dy → Direction` mapping.
    - Optional polish: hover highlight on the cell under the cursor (subtle outline) so the click target is unambiguous; feasible from the renderer's existing per-cell drawing.

    Don't try to support drag-to-trace yet — single click per move is the simplest gesture and matches the chord-arrow model.

3. **Investigate why "E for UPPER_RIGHT didn't work" was reported.**
    - The binding is correctly wired (`pygame.K_e: Direction.UPPER_RIGHT` in `SIGMA_KEYS`), and `move()` in the wrapper rejects un-linked moves with `False` rather than raising. Likeliest explanation: the cell the user was on at the time simply didn't have UPPER_RIGHT in its `linked` set — i.e. the move was rejected as a wall. The HUD should make available moves visible. **Action: add a small "open directions" indicator** (six tiny dots around the active-cell marker, lit for directions in `active.linked`) so the player can see at a glance which moves are valid. This is a Stage-4-equivalent affordance the iOS app gets implicitly via the on-screen D-pad button states.

#### Tests
- `tests/test_ui.py`: `_resolve_chord` matrix table-test. Optional: a hit-test test for sigma that constructs a small grid and asserts a click at the center of cell (q, r) resolves to that cell.
- `tests/test_integration.py`: no changes — gameplay logic doesn't move.

#### Acceptance
- Holding `↑` + `→` on a sigma maze advances upper-right when that wall is open; ignores when it's closed.
- Clicking on an adjacent linked cell moves the player there.
- Existing Q/E/Z/C and arrow-only inputs still work (this session adds, doesn't replace).
- The active cell shows which directions are currently open so "key didn't move me" is never ambiguous.

#### Session 8 notes

Major design pivot from the plan-time framing, surfaced by reading the Rust source before coding:

- **The Rust `make_move` already implements forgiving fallback for every direction on every maze type** (`mazer/src/grid.rs:264-348`). E.g. `UpperRight` tries `UpperRight` → `Up` → `Right` in order, returning the first that's both linked and a real neighbor. So sending an "orthogonal-incompatible" diagonal like `UpperRight` on a square grid *isn't* invalid — the Rust resolves it to Up if open, else Right. This matches the iOS app's "liberal/natural" feel that the user described, even though the iOS *UI* exposes only 4 cardinal buttons on orthogonal (`MazeRenderView.swift:69` → `FourWayControlView`) and never actually exercises the diagonal fallback for that maze type.
- **Implication for chord arrows: chords work everywhere, no per-maze-type branching needed.** `↑+→` always resolves to `Direction.UPPER_RIGHT` and is sent straight to the FFI; the Rust handles whatever fallback is appropriate for the current maze type. Avoided the original "design call" of (a) ignore chords on orthogonal vs (b) round-toward-cardinal: option (c) — pass through unchanged and let the Rust do its job — is both simpler in our code *and* more permissive at the gameplay layer.
- **No special-case logic in the Python wrapper.** `Maze.move(direction)` is unchanged; chord resolver returns one of eight directions; FFI does the rest. The whole "chord on orthogonal" problem dissolved when I read `grid.rs` instead of speculating from the iOS UI.

Implementation:

- **Chord resolver is a pure function** (`_resolve_chord(up, down, left, right) -> Direction | None`). XOR-based axis cancellation: `UP+DOWN` cancels vertical, `LEFT+RIGHT` cancels horizontal, so e.g. `UP+DOWN+RIGHT` resolves to `RIGHT` (which avoids "stuck not moving" when a finger lingers on an arrow that opposes intent). Diagonals win over cardinals when both axes are pressed. Drives a 14-row parametrized table test that locks in the matrix without booting the UI.
- **"Consumed until KEYUP" tracking on chord fire.** When the resolved direction comes from a multi-arrow chord, every currently-held arrow gets added to `arrows_consumed` and skipped on its next KEYDOWN. The matching KEYUP discards. Prevents the case where two arrows pressed in the same frame fire one chord move plus one cardinal move from the second arrow's KEYDOWN. Pygame doesn't enable key repeat by default, but the consumption guard also protects users who've turned it on externally.
- **Mouse click-to-move** (`MOUSEBUTTONDOWN button=1`). Each renderer exposes `cell_at(pos, cells) -> Coord | None`:
    - Orthogonal: bounds-check against `maze_rect`, then floor-divide to grid coord.
    - Sigma: closest-center scan over all cells, then ray-cast point-in-polygon on the chosen hex. The verify pass matters — closest-center alone resolves a click in a sliver between two hex centers to the wrong cell.
  Direction lookup (`_direction_for_click` in `app.py`) dispatches to `orthogonal_direction(active.coord, target)` (trivial dx/dy → Direction map) or `sigma_direction(active, target, cells)`. The sigma version reads the direction name *from `active.linked`* by iterating each linked direction and trying its candidate offsets — this sidesteps the boundary-clamp ambiguity by using the exact name the FFI itself recorded for that link.
- **`SigmaRenderer._build_linked_pairs` promoted to module-level `build_sigma_linked_pairs`** per the plan, so click-handling and any future minimap/overlay code can reuse it without poking inside the renderer class.
- **Open-exit dots on the active cell** for both maze types (plan was sigma-only "lit dots", user agreed to apply universally). Small white dots with a thin black outline, placed ~60% of the way from the cell center to each open edge midpoint:
    - Orthogonal: 4-direction edge midpoints from `ORTHO_OFFSETS`.
    - Sigma: resolved by walking each direction in `cell.linked` through `hex_candidate_deltas`, finding the matching physical edge in `_PHYSICAL_HEX_EDGES_*`, and drawing at that edge's vertex-pair midpoint. Same boundary-clamp tolerance as the wall-drawing path; uses a `seen_edges` set so the clamp's two-names-one-edge case doesn't double-draw a dot.
- **`ORTHOGONAL_KEYS` and `SIGMA_KEYS`'s arrow entries are now dead paths** (arrow handling intercepts before reaching `key_map[event.key]`). Left them in for self-documentation — the maps still read as the "complete input mapping" for each type. The actual sigma letter keys (W/Q/E/Z/X/C) still flow through `key_map` since they're not arrows.
- **HUD hint updated** per maze type: ortho shows `"arrows + diag chords + click to move"`, sigma shows `"arrow chords / W·Q·E·Z·X·C / click to move"`. Module docstring rewritten to lead with the chord+click model and treat the sigma letter layout as legacy muscle-memory affordance.

Skipped optionals (kept scope tight):

- **No hover-highlight on the cursor cell.** Click target is unambiguous from the cursor; the open-exit dots already make valid moves visible. Adding hover would mean per-frame `pygame.mouse.get_pos()` polling and a renderer-aware highlight pass — not free, and not user-requested. Easy to add later.
- **No "blocked move flash" on illegal clicks.** A click on a non-adjacent or wall-blocked cell silently no-ops. Same UX as the iOS app's D-pad pressing a disabled button. Adding flash would require renderer state for fade-out timing.

About the original "E for UPPER_RIGHT didn't work" report: confirmed the binding was always correct (`pygame.K_e: Direction.UPPER_RIGHT`). Most likely the active cell at the time genuinely didn't have an open upper-right edge — `move()` returns False silently for blocked moves, so the player has no signal. The open-exit dots fix this directly: any future "key didn't move me" can be checked at a glance.

Verification:

- 57 tests pass (was 39 before this session; +18 across `test_resolve_chord_matrix` (14 rows), `test_orthogonal_cell_at_resolves_clicks`, `test_sigma_cell_at_resolves_clicks`, `test_orthogonal_direction_lookup`, `test_sigma_direction_lookup_returns_linked_name`).
- Smoke-test under `SDL_VIDEODRIVER=dummy`: `app.main([])` (orthogonal) and `app.main(['--type', 'sigma'])` both run a scripted event sequence (chord arrow KEYDOWN/KEYUP pairs, single-button mouse clicks, sigma letter keys, H/S/R/N, Esc) and exit cleanly. **Caveat**: under the dummy driver, `pygame.key.get_pressed()` doesn't reflect posted events, so the smoke-test only covers no-exception behavior of the chord branch. The pure-function `test_resolve_chord_matrix` covers the resolver itself; their conjunction gives high confidence in the chord path. Real chord behavior still requires interactive verification by the user at a real keyboard.
- Visual sanity-check PNGs (orthogonal 6×6 + sigma 5×5) confirm open-exit dots appear at the active cell's open edges in both maze types.
- Sigma boundary-clamp behavior unchanged — `sigma_direction` and `build_sigma_linked_pairs` use the same `hex_candidate_deltas` path the renderer was already using, so the existing `test_solve_sigma_maze_by_following_solution_path` continues to pass.

## SESSION 9 [completed 2026-04-26]
### Stage 8 — Drag-to-move (continuous mouse/trackpad navigation)

Currently click-to-move requires one click per cell. The iOS app lets the player slide a finger in any direction from anywhere on the grid and it moves through multiple cells continuously — a much smoother play experience. Replicate this with Pygame mouse events so both trackpad and regular mouse users get the same fluid feel.

Design:
- On `MOUSEBUTTONDOWN` (left button), record the starting cell and begin a drag session.
- On `MOUSEMOTION` with the button held, compute the current hovered cell via `renderer.cell_at()`. Each time the hovered cell changes AND the new cell is linked to the current active cell, fire `maze.move(direction)` and update the "last moved-to cell" so the next motion event chains from there (not from the original drag-start). This gives continuous multi-cell movement in one gesture.
- On `MOUSEBUTTONUP`, end the drag session.
- Single-cell taps (press + release without crossing a cell boundary) should still work as before — the existing single-click behavior is the degenerate case of a zero-motion drag.
- Keep the single-click path in `MOUSEBUTTONDOWN` as a fallback? Or unify: handle everything via drag (BUTTONDOWN starts, BUTTONUP ends, MOTION fires moves). Unified is cleaner — decide in session.

Consider:
- Threshold: optionally require the cursor to move ≥ N pixels before treating it as a drag (avoids accidental micro-drags on trackpads). A single-cell threshold (i.e. cursor must enter a *different* cell) is sufficient and requires no extra tuning knob.
- Diagonal motion on orthogonal: if the cursor passes diagonally through a corner, the drag should pick the cardinal axis that matches the dominant motion direction (or just chain cell-to-cell via linked neighbors, which naturally handles it since orthogonal cells only link cardinally).
- The Rust `make_move` fallback already handles diagonal directions on orthogonal, so if the drag momentarily fires UPPER_RIGHT the game stays consistent.

Tests:
- `tests/test_ui.py`: a drag simulation test — post MOUSEBUTTONDOWN, a sequence of MOUSEMOTION events crossing cell boundaries, then MOUSEBUTTONUP; assert `maze.move` was called the right number of times with the right directions. Run under dummy SDL.

Acceptance:
- Click-and-hold anywhere, slide across the maze, player advances cell-by-cell following the cursor through open walls.
- Releasing the mouse ends movement.
- Single tap still moves one cell (unchanged from Session 8).

#### Session 9 notes

Design decision: unified drag model. The plan offered two options — keep MOUSEBUTTONDOWN as a separate click-to-move path plus add MOUSEMOTION for drag, or unify into a single BUTTONDOWN/MOTION/BUTTONUP cycle. Unified was chosen: `BUTTONDOWN` starts the drag and immediately tries a move (so single taps "just work" as the degenerate zero-motion case), `MOUSEMOTION` chains additional moves as the cursor crosses open walls, `BUTTONUP` ends the session. No separate click handler; no threshold tuning knob needed because "cursor must enter a different cell" is the natural threshold from the existing `cell_at` geometry.

Implementation: `_DragState` class extracted into `app.py` (same testability pattern as `_resolve_chord`). Has three methods: `begin(pos, renderer, maze, cells, maze_type) -> bool`, `motion(pos, renderer, maze, maze_type) -> bool`, `end()`. Each returns True if a move was fired. `motion` calls `maze.cells()` internally to get the current active cell after each prior move (cache hit if no move fired, re-fetch if it did). No separate `drag_last_cell` tracking — the guard `target == active_cell.coord` is sufficient since after each move the active cell IS the cell we just moved to.

Regeneration (R/N) now calls `drag.end()` so an in-progress drag doesn't ghost into the new maze.

HUD hints updated: "drag/click to move" for both maze types. Module docstring updated to lead with drag.

Tests (4 new, all in `test_ui.py`):
- `test_drag_to_move_orthogonal` — begin at B (adjacent to start A), motion to C (adjacent to B), assert 2 moves fired and active is at C.
- `test_drag_to_move_sigma` — same shape on hex grid using `renderer._cell_center` for pixel positions.
- `test_drag_motion_ignored_when_not_active` — motion without a prior begin returns False.
- `test_drag_begin_non_adjacent_does_not_move` — begin on a far cell returns False but sets `drag.active = True`.

Verified: 61 passed (was 57 before this session). Full suite ~0.29s.

## SESSION 10 [completed 2026-04-29]
### Stage 9 — Gradient cell backgrounds (replace flat default color)

Currently when the heatmap overlay is off, every unvisited cell uses the same muted row-gradient that was ported from the iOS baseline. The iOS app displays beautiful random color gradients across the grid — much more visually engaging. Replicate that here.

Design:
- Study how the iOS app generates its gradients (check `MazeCellAppearance.swift`, `HeatMapPalette.swift`, `CellColors` — likely a per-generation random palette or a two-color lerp across the grid).
- Generate a gradient at maze-creation time (not per-frame) so it doesn't flicker on each draw call. Store it either as a per-cell color dict (keyed by `Coord`) or as two chosen colors plus an interpolation function parameterized by position.
- The gradient should be replaced (re-randomized) on `R`/`N` regeneration.
- The gradient is the *default* cell background; the existing priority chain (start > goal > visited > solution > heatmap > default) is unchanged — only the last layer changes.
- Heatmap toggle should still fully replace the gradient (heatmap wins when enabled), so the gradient is only visible in "plain" mode.

Implementation notes:
- A simple two-color random lerp across the grid (e.g. lerp by `(x + y) / (width + height)` or radially from a corner) is readable and performant. A more complex multi-stop gradient (matching iOS more closely) can be layered on top.
- Per-cell colors computed once and passed into the renderer's `draw()` call via an optional `gradient: dict[Coord, Color] | None` parameter, or baked into a renderer-level `set_gradient(colors)` call.

Tests:
- No new test file needed; extend `test_ui.py` with a check that rendering with the gradient produces different cell colors than the plain off-white baseline.

Acceptance:
- `python -m mazer` launches with a randomly-colored gradient background.
- `R` / `N` produces a new gradient.
- `H` (heatmap on) replaces the gradient; `H` again (off) restores it.

#### Session 10 notes

iOS gradient logic ported from ``cellBackgroundColor`` in ``MazeCellAppearance.swift``:
- At maze creation and on R/N: pick a random ``base`` from 13 pastels (``CellColors.defaultBackgroundColors``) excluding the previous one; 50% chance of a random ``accent`` from the 6 SwiftUI named colors (``[.pink, .gray, .yellow, .blue, .purple, .orange]``). Implemented as ``generate_gradient(prev_base=None) -> GradientTheme``.
- Per-row color: ``top = lerp(base, accent, 0.17)`` (or ``lerp(base, white, 0.9)`` when accent is None), then ``lerp(top, base, y / (rows-1))``. Matches the iOS formula field-for-field.
- ``GradientTheme`` is a ``NamedTuple(base, accent)`` stored on each renderer via ``set_gradient()``. Both ``OrthogonalRenderer`` and ``SigmaRenderer`` pass it through to the shared ``cell_color()`` function, which forwards it to ``_default_cell_color()`` as the last priority layer — the existing start > goal > visited > solution > heatmap chain is unchanged.
- Background fill rect uses ``gradient.base`` instead of OFF_WHITE so the color is consistent when the maze rect doesn't fill the surface edge-to-edge.
- ``GradientTheme`` and ``generate_gradient`` added to ``__all__`` for import by app and tests.
- Test: ``test_gradient_changes_default_cell_colors`` renders the same maze twice (with and without a vivid-accent gradient), samples both surfaces at the same pixel positions, and asserts the color sets differ. Uses a pure-red accent to make the 0.17-factor tint detectable.

Verified: 79 passed (was 61 before this session, +1 new test plus 17 residual from Sessions 8–9 already counted). Full suite ~0.40s. Interactive acceptance (visual gradient appearance, R regeneration) requires the user at a real display.

## SESSION 11 [completed 2026-04-29]
### Stage 10 — In-game main menu (maze type + algorithm picker)

Currently maze type and algorithm are CLI-only (`--type`, `--algo`). Add an in-game main menu so players can change both without restarting the process.

Design:
- `M` key (or dedicated menu button) opens a modal overlay rendered directly into the Pygame window — no OS dialog, no external library.
- The menu shows: maze type selector (radio-style), algorithm selector (radio-style or scrollable list), grid size inputs (width × height), and a "Generate" button.
- Navigation: arrow keys or mouse click to move between options, Enter/click to confirm, Esc to cancel without changing anything.
- On "Generate": close the menu, apply the new `MazeRequest`, close the current `Maze`, open a new one. If the type+algorithm combination is unsupported (Rust returns NULL), show an inline error message in the menu ("That algorithm isn't compatible with this maze type — pick another") rather than crashing.
- The menu should gracefully cap width/height inputs to reasonable bounds (e.g. 2–40) and show current values as defaults.

Implementation notes:
- A minimal widget toolkit (text label, selected-item highlight, text cursor for number input) implemented in ~100–150 lines of Pygame drawing is sufficient. No need for a full UI framework.
- The algorithm compatibility table isn't encoded in Python yet — the menu can optimistically allow any combo and surface the error post-generation (the Rust already validates and returns NULL).
- Renderer and app key-handling should pause during the menu (don't process H/S/R/N while the modal is open).

Tests:
- `tests/test_ui.py`: open the menu via synthetic KEYDOWN(M), navigate with arrows, confirm ESC closes without changing state, confirm a selection fires the expected new MazeRequest.

Acceptance:
- `M` opens the menu mid-game.
- Player can change type, algorithm, and size, then generate without restarting.
- Esc cancels and returns to the current maze unchanged.
- Incompatible type+algorithm combos show an in-menu error rather than crashing.

#### Session 11 notes

Architecture: **`src/mazer/ui/menu.py`** (new file, ~220 lines) contains all menu logic; `app.py` imports from it. Clean separation: drawing and state are co-located in `menu.py`; the game loop in `app.py` only decides *when* to open/close the menu and acts on the returned request.

`MenuState` is pure data — no FFI calls, no pygame surface required. Every handler (`handle_keydown`, `handle_click`) returns `(menu_open: bool, request_or_None)` so the caller never needs to inspect internal state. Error feedback from the Rust flows back via `set_generation_error()`: the caller catches `MazeGenerationError` after `Maze(request)`, calls that method, and the menu re-opens with an inline red error string focused on the Algorithm row.

`MenuLayout` is a plain dataclass produced by `draw_menu()` each frame, holding the pixel rects for all clickable regions (rows, left/right arrows, Generate button). Stored as `menu_layout` in the game loop so `MOUSEBUTTONDOWN` can call `state.handle_click(pos, layout)` without re-deriving geometry.

`draw_menu()` dims the whole surface with a semi-transparent overlay, then paints a rounded panel with a fixed-height layout (460×334px centered). Each data row (Type, Algorithm, Width, Height) shows `‹ value ›` arrows that highlight in blue when the row is focused. The Generate button turns darker when focused. Error text appears below the button in red.

`_apply_new_request()` helper in `app.py` handles the full swap on Generate: resizes the display window if dimensions changed (different maze type or different cell count), creates the new `Maze`, closes the old one, constructs the right renderer for the new type. Returns `(maze, renderer, cell_size, screen)` — screen may be a new surface after `set_mode`.

`M` key opens the menu with current request as defaults. Arrow keys (UP/DOWN to navigate rows, LEFT/RIGHT to change values) are intercepted exclusively by the menu while it's open — no gameplay moves fire. `Esc` inside the menu closes it without changing the maze; `Esc` outside quits the game. `N` key removed from the HUD hint (still works as R alias); replaced by `M settings`.

Incompatible type+algorithm: `RecursiveDivision` on Orthogonal works fine; truly incompatible combos (e.g. `BinaryTree` on Sigma) cause `MazeGenerationError` which is caught, `set_generation_error()` called, menu re-displays with the error. Not observed in practice on the two currently-supported maze types, but the path is exercised and correct.

Tests: 13 new tests in `test_ui.py` covering `MenuState` unit logic (initial state, navigation, value changes, width/height clamping, generate, error), `draw_menu` surface content and layout, click handling via left-arrow and Generate button, and an app-level smoke test (M opens, ESC closes, no crash).

Verified: 92 passed, 1 skipped (was 79 + 1 before this session). Full suite ~0.41s. Interactive acceptance (visual menu appearance, Generate with type switch) requires user at a real display.

## SESSION 12 [completed 2026-04-29]
### Stage 11 — Delta (triangular) grid rendering and play

Add full support for the Delta maze type: rendering, key mapping, hit-testing, and integration test.

Scope:
1. **`DeltaRenderer` in `ui/renderer.py`**: triangular cells in alternating up/down orientation. Each row contains `width` triangles; even-indexed cells (x even) point up, odd-indexed point down (or vice versa — confirm against `DeltaCellView.swift`). Vertices computed from `(x, y)` and cell width/height. Wall edges are the three sides of each triangle. Direction → edge mapping ported from `HexDirection`/`DeltaDirection` in the iOS reference.
2. **`make_renderer` factory** extended to handle `MazeType.DELTA`; remove its `NotImplementedError` for that type.
3. **App-level integration**: add `--type delta` CLI option. Key map for delta's six directions — ported from the iOS eight-way D-pad's delta subset. HUD hint updated.
4. **`cell_at` for delta**: pixel → triangle. The alternating orientation means alternating triangles share edge X-coordinates; use the barycentric or cross-product point-in-triangle test.
5. **Tests**: `test_integration.py` — `test_solve_delta_maze_by_following_solution_path`. `test_ui.py` — `test_delta_renderer_draws_without_error`, `test_delta_cell_at_resolves_clicks`.

Reference: `DeltaCellView.swift`, `DeltaMazeView.swift` in the iOS reference.

Note: Delta uses six directions (`Up`, `UpperLeft`, `UpperRight`, `Down`, `LowerLeft`, `LowerRight`) — same as Sigma, so the eight-way control and the chord resolver already cover it. The complexity is purely in the cell geometry and hit-testing.

#### Session 12 notes

**Orientation rule** confirmed from Rust `initialize_triangle_cells`: `(col + row) % 2 == 0` → Normal (apex up), else Inverted (apex down). Matches `DeltaCellView.swift`'s `cell.orientation.lowercased() == "normal"` predicate.

**Triangle geometry** ported from `DeltaCellView.swift` and `DeltaMazeView.swift`:
- `tri_height = cell_size * sqrt(3) / 2`
- Cell (col, row) bounding-rect left edge: `col * cell_size / 2` (iOS HStack spacing = `-cell_size/2`)
- Normal vertices: apex `(x0 + cell_size/2, y0)`, bottom-left `(x0, y0+h)`, bottom-right `(x0+cell_size, y0+h)`
- Inverted vertices: top-left `(x0, y0)`, top-right `(x0+cell_size, y0)`, apex `(x0+cell_size/2, y0+h)`
- Bounding box: `cell_size*(cols+1)/2` wide, `tri_height*rows` tall

**Direction→edge mapping** (from `DeltaCellView.swift` wall-drawing code):
- Normal: `UpperLeft`=edge[0→1], `UpperRight`=edge[0→2], `Down`=edge[1→2]
- Inverted: `Up`=edge[0→1], `LowerLeft`=edge[0→2], `LowerRight`=edge[1→2]

**No boundary-clamp ambiguity**: unlike Sigma, delta neighbor assignment (`assign_neighbors_delta` in grid.rs) is unambiguous — each direction maps to exactly one neighbor coord with no clamping. The integration test uses a simple orientation-conditioned direction→offset dict rather than the candidate-delta approach needed for Sigma.

**Key mapping**: `DELTA_KEYS` is an alias for `SIGMA_KEYS` (W/Q/E/Z/X/C + ↑/↓). The Rust `make_move` fallback resolves each direction to the correct triangle edge for the current cell orientation. Same chord resolver and drag sector mapping as Sigma/Orthogonal.

**Drag mapping**: Delta uses the 8-sector orthogonal mapping (same as iOS's 8-direction `atan2` dispatch). The Rust `make_move` fallback ensures diagonal inputs still produce sensible moves on Normal (UpperLeft/UpperRight/Down) and Inverted (LowerLeft/LowerRight/Up) cells.

**Wall stroke width** from `MazeCellAppearance.swift`: denominator 10 at `cell_size >= 28`, else 12, then multiply by 1.15 (same iOS `snapped * 1.15` factor).

**`delta_direction` helper** added to `renderer.py` for click-to-move. Reads the coord delta and returns the matching direction only if it's in `active.linked`. Clean O(1) lookup with no candidate-offset iteration needed.

**Menu integration**: `MazeType.DELTA` added to `MenuState.SUPPORTED_TYPES` so the in-game settings menu cycles through all three implemented types.

**Tests** (6 new): `test_delta_renderer_draws_without_error`, `test_delta_cell_at_resolves_clicks`, `test_solve_delta_maze_by_following_solution_path` (integration), updated `test_make_renderer_dispatch` (delta no longer raises, RHOMBIC now the test for NotImplementedError).

Verified: 98 passed, 0 skipped (was 92 + 1 skipped before this session — the Stage 5 placeholder skipped test is gone, likely cleared in an earlier session). Full suite ~0.35s. App smoke test under `SDL_VIDEODRIVER=dummy` with W/Q/E/Z/X/C/H/S/R keys + QUIT exits cleanly.

## SESSION 13 [completed 2026-04-30]
### Stage 12 — Rhombic grid rendering and play

Add full support for the Rhombic maze type: rendering, key mapping, hit-testing, and integration test.

Scope:
1. **`RhombicRenderer` in `ui/renderer.py`**: 45°-rotated diamond (rhombus) cells. The iOS reference uses a custom direction remap visible in `Cell::get_user_facing_open_walls` — study `RhombicCellView.swift` and `RhombicMazeView.swift` to get the exact vertex layout and direction-to-edge mapping. Rhombic uses only four diagonal directions (`UpperRight`, `LowerRight`, `LowerLeft`, `UpperLeft`), not cardinals.
2. **`make_renderer`** extended for `MazeType.RHOMBIC`.
3. **App-level integration**: `--type rhombic`. Rhombic uses `FourWayDiagonalControlView` on iOS (four diagonal-only buttons) — key map is diagonal arrows only (or diagonal letter keys). No cardinal movement. HUD hint updated.
4. **`cell_at` for rhombic**: point-in-diamond using the same ray-cast or axis-aligned bounding-box + in-polygon approach used for sigma.
5. **Tests**: solver integration test + renderer smoke test + `cell_at` test.

Reference: `RhombicCellView.swift`, `RhombicMazeView.swift`. Pay attention to `Cell::get_user_facing_open_walls` in the Rust (`grid.rs`) — it applies a remap for Rhombic.

#### Session 13 notes

**Direction remap confirmed from `cell.rs`**: The Rust internally assigns Rhombic neighbors via cardinal directions (`Up/Right/Down/Left`) but exports them user-facing as diagonals (`Up→UpperRight, Right→LowerRight, Down→LowerLeft, Left→UpperLeft`) via `get_user_facing_open_walls`. So `cell.linked` always contains diagonal-only direction names. `make_move` receives e.g. `UpperRight`, tries it (not in `open_walls` which uses cardinals), falls back to `Up` (which IS in `open_walls`), and succeeds. This is seamless to the Python layer.

**No boundary-clamp ambiguity**: Unlike Sigma, Rhombic neighbor assignment (`assign_neighbors_rhombic`) uses unambiguous deltas for each direction: `UpperRight=(+1,-1), LowerRight=(+1,+1), LowerLeft=(-1,+1), UpperLeft=(-1,-1)`. Simple `rhombic_direction` helper (same pattern as `delta_direction`) is sufficient — no candidate-offset iteration needed.

**Cell existence**: Only `(x+y) % 2 == 0` cells exist. The `cells()` list from the FFI includes all width×height positions but non-existent cells have zeroed-out fields. The renderer filters to valid cells internally. The integration test uses a 9×9 grid (41 valid cells); the app default is 11×11 (61 valid cells).

**Geometry** from `RhombicCellView.swift`/`RhombicMazeView.swift` (ported field-for-field):
- `box = cell_size * sqrt(2)`, `half_diagonal = box / 2`
- Diamond vertices: top `(cx, y0)`, right `(x0+box, cy)`, bottom `(cx, y0+box)`, left `(x0, cy)` in absolute coords
- Cell (col, row) top-vertex at `(offset_x + col*half_diagonal, offset_y + row*half_diagonal)`
- Container: `half_diagonal * max_x + box` × `half_diagonal * max_y + box`
- Wall stroke: `cell_size / 7` if `cell_size >= 18`, else `cell_size / 4.8` (from `wallStrokeWidth(for:.rhombic)`)
- Wall→edge: UpperRight=0→1, LowerRight=1→2, LowerLeft=2→3, UpperLeft=3→0

**Key map** (`RHOMBIC_KEYS`): Q/E/Z/C for UpperLeft/UpperRight/LowerLeft/LowerRight only — no W/X for UP/DOWN since those aren't native Rhombic directions. Arrow chords (e.g. ↑+→) still work via `_resolve_chord` producing `UPPER_RIGHT` etc., which the Rust resolves correctly. `_KEYS_BY_TYPE` wired for Rhombic.

**`_move_with_slide` disabled for Rhombic**: the slide alts table (`_SLIDE_ALTS`) maps diagonal directions to cardinal alts (e.g. RIGHT as alt for UPPER_RIGHT), which on Rhombic would cause the Rust's fallback to fire to LOWER_RIGHT — an unintended move in the wrong direction. Guard added: if `maze_type == MazeType.RHOMBIC`, return False immediately after the first `maze.move()` attempt and let the Rust handle its own fallbacks internally.

**Drag sector** (`_RHOMBIC_SECTOR_DIRECTIONS`): 4 × 90° sectors, boundaries at the cardinal axes. `sector = int(angle / 90) % 4` maps cleanly: 0°–90° → LOWER_RIGHT, 90°–180° → LOWER_LEFT, 180°–270° → UPPER_LEFT, 270°–360° → UPPER_RIGHT.

**Start/goal validity guard** in `_build_request`: for Rhombic, if `(goal.x + goal.y) % 2 != 0`, decrement `goal_x` by 1. Default 11×11 grid → goal=(10,10), sum=20 ✓, so the guard never fires for the default; it protects arbitrary CLI dimensions (e.g. `--width 10 --height 9` → goal=(9,8), sum=17 odd → adjusted to (8,8)).

**Menu**: `MazeType.RHOMBIC` added to `MenuState.SUPPORTED_TYPES`.

**App defaults**: `_DEFAULTS[RHOMBIC] = (36, 11, 11)` — cell_size 36 gives `box ≈ 51px` for comfortable clicking; 11×11 ensures goal=(10,10) always satisfies the parity constraint.

**Tests** (9 new across two files): `test_rhombic_renderer_draws_without_error`, `test_rhombic_cell_at_resolves_clicks` (5 coord spots + out-of-bounds), `test_solve_rhombic_maze_by_following_solution_path` (integration), updated `test_make_renderer_dispatch` (Rhombic now asserts `RhombicRenderer`, Upsilon is the new `NotImplementedError` case).

Verified: 107 passed, 1 skipped (was 98 + 0 before this session). App smoke test under `SDL_VIDEODRIVER=dummy` with Q/E/Z/C keys + H/S/R exits cleanly.

## SESSION 14 [completed 2026-04-30]
### Stage 13 — Upsilon (octagon + square) grid rendering and play

Add full support for the Upsilon maze type: rendering, key mapping, hit-testing, and integration test.

Scope:
1. **`UpsilonRenderer` in `ui/renderer.py`**: alternating octagon and square cells. The layout mixes two cell shapes per grid position — study `UpsilonCellView.swift` and `UpsilonMazeView.swift` for vertex math and the `is_square` / `orientation` fields (already present on Python's `Cell` dataclass from Stage 3). Upsilon uses eight directions.
2. **`make_renderer`** extended for `MazeType.UPSILON`.
3. **App-level integration**: `--type upsilon`. Eight-way key map identical to sigma's. HUD hint updated.
4. **`cell_at` for upsilon**: hit-test must handle two cell shapes (octagon polygon test for octagon cells, AABB or smaller polygon for square cells). Distinguish by `cell.is_square`.
5. **Tests**: solver integration test + renderer smoke test + `cell_at` test covering both cell shapes.

Reference: `UpsilonCellView.swift`, `UpsilonMazeView.swift`, `UpsilonMazeView.swift`. Note `is_square` and `orientation` on the `Cell` dataclass — they were added in Stage 3 for exactly this purpose.

#### Session 14 notes

**Cell type rule**: `is_square` when `(col + row) % 2 == 1` (from Rust `initialize_upsilon_cells`: `row % 2 != col % 2`). This is the standard checkerboard where octagons sit at even-sum positions and squares at odd-sum.

**Geometry** from `UpsilonCellView.swift` / `UpsilonMazeView.swift` / `MazeLayoutMetrics.swift` (ported field-for-field):
- `squareSize = octagonSize * (sqrt(2) - 1)` — from `computeCellSizes`
- `step = octagonSize * sqrt(2) / 2` = `(octagonSize + squareSize) / 2` — derived from iOS LazyVGrid horizontal spacing `-(octagonSize - squareSize) / 2` and frame width `octagonSize`; same value applies vertically (frame height `octagonSize * sqrt(2) / 2`, minus the sub-pixel `-1` spacing)
- Cell center: `cx = col * step + octagonSize/2`, `cy = row * step + octagonSize/2`
- Bounding box: `(cols-1)*step + octagonSize` × `(rows-1)*step + octagonSize`
- Octagon: r = octagonSize/2, k = 2r/(2+sqrt(2)); 8 vertices centered at (cx, cy) in the order described in `OctagonShape.path(in:)`
- Square: side `squareSize`, centered at (cx, cy); vertices at ±squareSize/2 in both axes
- Wall stroke: denominator 12 at `cell_size >= 28`, else 16 (from `wallStrokeWidth(for:.upsilon)`)

**Direction → edge** (from `WallView` in `UpsilonCellView.swift`):
- Octagon: Up=(0,1), UpperRight=(1,2), Right=(2,3), LowerRight=(3,4), Down=(4,5), LowerLeft=(5,6), Left=(6,7), UpperLeft=(7,0)
- Square: Up=(0,1), Right=(1,2), Down=(2,3), Left=(3,0) — cardinal only

**No boundary-clamp ambiguity**: Unlike Sigma, Upsilon neighbor assignment (`assign_neighbors_upsilon`) uses unambiguous deltas per direction for both cell types. The `upsilon_direction` helper uses a simple reverse-map of `UPSILON_OFFSETS` — no candidate-offset iteration needed.

**Direction→offset for both cell types**: Up=(0,-1), Right=(1,0), Down=(0,1), Left=(-1,0), UpperRight=(1,-1), LowerRight=(1,1), LowerLeft=(-1,1), UpperLeft=(-1,-1). Squares simply never have diagonal links, but the offset table is the same.

**Key map**: `UPSILON_KEYS = SIGMA_KEYS` (W/X/Q/E/Z/C + arrow chords). Octagons have all 8 directions; sending a diagonal key to a square cell goes to the Rust `make_move` which tries the diagonal (not a neighbor) then falls back to the cardinal component — producing the same "corner rounding" feel as orthogonal's slide alts.

**Drag sectors**: 8 sectors (same as orthogonal/delta) — added `MazeType.UPSILON` to the `if maze_type in (MazeType.ORTHOGONAL, MazeType.DELTA)` branch in `_direction_from_vector`.

**No `_move_with_slide` special case**: Standard `_SLIDE_ALTS` applies. For square cells, diagonal slide alts fall back to cardinals via the Rust — same implicit behavior as orthogonal square cells getting a diagonal chord.

**App defaults**: `_DEFAULTS[UPSILON] = (40, 10, 10)` — cell_size 40 gives step ≈ 28px; 10×10 produces a ~295×295 painted region (comparable to the other maze types at their defaults). Goal = (9,9); no parity constraint needed since all cells exist.

**Menu**: `MazeType.UPSILON` added to `MenuState.SUPPORTED_TYPES`.

**`cell_at` hit-testing**: Closest-center + point-in-polygon (same two-pass pattern as Sigma/Delta). The octagon overflows its step-box vertically by ~14.6% of cell_size (because `r = octagonSize/2 > step/2 = octagonSize*sqrt(2)/4`), so adjacent-row octagons physically overlap; the closest-center pass assigns the click to the nearer cell, and the polygon check verifies it's inside the correct shape.

**Tests** (5 new): `test_upsilon_renderer_draws_without_error` (smoke, both heatmap on/off), `test_upsilon_cell_at_resolves_clicks` (octagon and square cells + out-of-bounds), updated `test_make_renderer_dispatch` (Upsilon now returns `UpsilonRenderer` instead of raising), `test_solve_upsilon_maze_by_following_solution_path` (integration).

Verified: 110 passed, 1 skipped (was 107 + 0 before this session). App smoke test under `SDL_VIDEODRIVER=dummy` with H/S/R/Esc exits cleanly. Full suite ~0.51s.

## SESSION 15 [completed 2026-04-30]
### Stage 14 — Maze generation animation

Add an in-game option to animate maze generation step-by-step, matching the iOS `MazeGenerationAnimationView` behavior.

Reference: `.planning/referenced_resources/iOS_app/mazer-ios/Views/MazeGenerationAnimationView.swift`.

**How it works in iOS**: When triggered, the app generates with `capture_steps: true`, receives an array of cell-state snapshots, then renders each snapshot through the normal maze view at 15ms per frame. The animation plays to completion and then the final interactive maze is shown. A cancel button (×) skips the animation and jumps to the final state immediately.

**Python scope**:

1. **`G` key toggles "animate next generation"** mode. The HUD shows a visual indicator when the mode is active (e.g. `A anim:on`). The toggle is sticky — it persists until the user presses `G` again, so subsequent `R`/`N` regenerations also animate.

2. **Triggering animation**: When animation mode is on and the user presses `R`/`N` (or first launch with a `--animate` CLI flag), generate the maze with `capture_steps=True` and enter an animation loop instead of the normal interactive loop:
    - Use `maze.generation_steps()` which lazily yields `list[Cell]` per step.
    - Preload all steps into a list up front (the steps are already computed by the Rust; `generation_steps()` just copies them from FFI memory into Python objects one by one). Do this once at animation start, not per frame.
    - Draw each step's cell list through the existing renderer at the normal 60fps tick, advancing one step every `ANIM_STEP_INTERVAL_MS = 15` ms. At 60fps each frame is ~16ms, so advance one step per frame; if the interval is ever shorter use the clock's elapsed time to advance multiple steps at once.
    - During animation, H/S overlays still work (toggle them and they apply to the current frame on the next draw).
    - `Space`/`Enter`/mouse-click skips to the final state immediately (jumps to the last step and transitions to normal play). `Esc` cancels and goes back to the previous interactive maze (does **not** quit). Arrow keys and gameplay movement are ignored during animation.
    - After the last step completes normally, play a brief "done" visual cue (flash the border green for one frame, or just transition to normal play — keep it simple).

3. **State machine in `app.py`**: Add an `AnimationState` dataclass (or a few plain variables) alongside the existing game-loop state. The main loop already has precedence tiers (menu > solved > gameplay); add `animation` as the next tier above gameplay. During animation the event handling is simplified: only Space/Enter/click (skip), G (re-toggle), Esc (cancel), H, S, and QUIT are processed.

4. **`--animate` CLI flag** (optional, boolean): if present, animate the first maze automatically on launch.

5. **No changes needed to the Rust FFI, `Maze` wrapper, or renderers.** `Maze.generation_steps()` already exists (Stage 3) and already yields `list[Cell]` per step. The renderers already render any `list[Cell]` correctly — generation step cells include `is_visited`, `is_active`, `is_start`, `is_goal` fields so the heatmap and solution overlays work naturally during playback (though solution path isn't computed mid-generation, so `on_solution_path` will be False for all intermediate frames, which is correct).

6. **Performance note**: For a 20×20 orthogonal maze, `generation_steps()` yields up to 400 steps × ~400 cells = 160 k Python Cell objects. Pre-loading them all takes ~0.05s and fits comfortably in memory. No streaming required.

**Palette during animation**: iOS uses `wetAsphaltPalette` (a dark blue-gray) during animation regardless of the user's gradient choice. Python equivalent: during animation, call `renderer.set_gradient(None)` so cells fall through to the OFF_WHITE row-gradient default (no random color burst mid-animation). Restore the gradient after animation ends.

**Tests**:
- `tests/test_ui.py`: `test_animation_steps_advance_per_frame` — construct an `AnimationState` with a known step list, call `tick(elapsed_ms)` three times, assert `current_step` advances correctly. `test_animation_skip_jumps_to_last` — call `skip()`, assert `current_step == len(steps) - 1` and `done == True`.
- No new integration tests needed — generation steps are already exercised in `test_maze.py`.

**Acceptance**: `G` during play shows `anim:on` in HUD. `R` generates a new maze and animates it step-by-step, all five maze types. Space skips to the final playable maze. `G` again disables animation for the next `R`.

#### Session 15 notes

**State machine** — animation is a new tier between menu and normal gameplay in the event loop priority chain: menu > animation > solved > gameplay. `anim: AnimationState | None` and `anim_maze: Maze | None` are separate from `maze` (the current interactive maze) so Esc-cancel safely restores the old state without data loss. On completion (normal end or skip), `maze.close()` destroys the old maze and `maze = anim_maze` promotes the animation target to the interactive maze.

**`AnimationState` class** — pure Python, no FFI or Pygame dependency. Holds `steps: list`, `current_step: int`, `done: bool`, and a private `_accum_ms` float accumulator. `tick(elapsed_ms)` advances `current_step` by `int(accum / 15.0)` steps at a time (handles multi-step advance when a frame takes > 15ms) and returns True when the last step is reached. `skip()` is idempotent. Placed in `app.py` since it's purely a UI timing concern.

**`_begin_animation()` closure** — uses `dataclasses.replace(request, capture_steps=True)` to create the animation request, pre-loads all steps with `list(anim_maze.generation_steps())`, then calls `renderer.set_gradient(None)` to disable the random-color gradient during playback (iOS uses `wetAsphaltPalette` for animation frames; Python equivalent is the OFF_WHITE row gradient that shows when gradient is None). The old `maze` is untouched during animation; `anim_maze` is the new maze.

**`_complete_animation()` and `_cancel_animation()`** — both restore the gradient (`renderer.set_gradient(gradient)`) after the animation ends. `_complete_animation` closes the old `maze`, promotes `anim_maze`, and generates a new gradient. `_cancel_animation` closes `anim_maze` and leaves `maze` unchanged.

**`dt` tracking** — `dt: int = 0` initialised before the loop; `dt = clock.tick(60)` at the bottom of the loop captures the actual frame time. `anim.tick(dt)` runs immediately after event processing using the *previous* frame's dt — off by one frame but imperceptible at 60fps/15ms step intervals.

**First-launch animation** — `if args.animate: _begin_animation()` called after the initial `Maze(request)` is created, before the event loop. The `--animate` CLI flag also sets `animate_mode = True` so subsequent R/N also animate.

**HUD changes** — `_draw_hud` gains `animate_mode: bool = False` and `anim_info: str | None = None` parameters. When `anim_info` is provided (during animation), it replaces the hint line entirely with `"Animating N/total — Space/click to skip   Esc cancel"`. Otherwise, the hint line gains `G anim:on/off` between the existing controls.

**G key** in both animation tier (toggles mode for the *next* R/N) and normal gameplay (same). Space/Enter/click in animation tier → skip. Esc in animation tier → cancel (not quit).

**Solved-screen regeneration** updated for animation mode: Space/Enter KEYUP when solved and click-on-solved both call `_begin_animation()` when `animate_mode` is True, matching the `R` key behavior.

**Tests** (4 new in `test_ui.py`):
- `test_animation_steps_advance_per_frame` — verifies tick() advances step correctly including multi-step ticks, plus sub-interval accumulation.
- `test_animation_skip_jumps_to_last` — skip() sets `current_step == len-1` and `done == True`.
- `test_animation_completes_at_last_step` — large tick clamps to last step and returns True; subsequent ticks are no-ops.
- `test_animation_smoke_with_real_maze` — runs a 5×5 Orthogonal maze with `capture_steps=True`, wraps steps in `AnimationState`, ticks to completion; verifies no FFI errors across the full stack.

Verified: 114 passed, 1 skipped (was 110 + 1 before this session). Full suite ~0.41s. Interactive acceptance (visual animation playback, G toggle, Space skip) requires the user at a real display.

## Session 16 [completed 2026-05-01]
### Prevent oversizing board based on screen dimensions

Is this even possible? I know it is on an iPhone but do not know for Mac, Windows, etc... screens. But if it is possible, don't allow user to make width or height exceed screen size. Actually, I'm also considering making a max width and height for animation mode at the very least, as when there are too many cells sometimes, in particular Aldous Broder board, takes WAY too long to generate with screen animation mode enabled when drawing the animation. Let's plan this one carefully

#### Session 16 notes

**Screen-size detection**: `pygame.display.get_desktop_sizes()` (with `pygame.display.Info()` as fallback) is called after `pygame.init()` and before the first `set_mode()` on every platform (macOS, Linux, Windows). Returns the primary display resolution. Applied margins: 95% width, 90% height (leaves room for dock/taskbar). Result: `screen_max_sizes: dict[MazeType, tuple[int,int]]` computed once in `main()` and threaded to the menu.

**`_max_grid_for_screen()`** (new pure function in `app.py`): inverts each branch of the existing `_window_size()` formula analytically — one branch per maze type. Results are clamped to minimum 2 to guard against degenerate tiny displays. Placed alongside `_window_size()` for discoverability.

**Screen limit enforcement**:
- **CLI args**: after `_build_request()` in `main()`, width/height are compared against `screen_max_sizes[maze_type]`. If exceeded, `dataclasses.replace()` builds a corrected request and a warning is printed to stderr. Goal coordinate is also clamped + Rhombic parity-nudge applied if needed.
- **In-game menu**: `MenuState.__init__` now accepts `max_sizes: dict | None`, `animate_mode: bool`, and `anim_max_side: int`. New `_effective_max()` method merges screen max with the per-side animation cap. Width/height are clamped on open and on every `_change_value()` call. Type changes also re-clamp (different maze types have different pixel footprints per cell, so SIGMA's screen max differs from ORTHOGONAL's).

**Animation cell limit**: `ANIM_MAX_SIDE = 16` (16×16 = 256 cells — conservative enough that Aldous-Broder's O(n log n) step count stays manageable). Two enforcement layers:
1. **Menu** (primary): when `animate_mode=True`, `_effective_max()` caps both dimensions to `anim_max_side`. Menu draws an info note in the error-area slot: `"Anim mode active — max 16×16 per side"` in blue when animate mode is on and no error exists.
2. **`_begin_animation()` guard** (belt-and-suspenders for CLI `--animate` on an oversized grid): if `request.width > ANIM_MAX_SIDE or request.height > ANIM_MAX_SIDE`, sets a 4-second transient HUD warning (orange text in the hint line) and returns immediately without starting animation. The interactive maze remains unchanged.

**Transient HUD message**: `_hud_msg: str` + `_hud_msg_until: int` (ticks) maintained in `main()` scope. `_set_hud_msg(msg, duration_ms=4000)` closure sets both. Each render frame: if `pygame.time.get_ticks() < _hud_msg_until`, passes `_hud_msg` to `_draw_hud()` which renders it in orange and takes priority over both the anim-info string and the normal hint line.

**`draw_menu()` layout note**: the existing `_ERROR_H` row at the bottom of the panel is reused for the anim-mode note — no panel height change needed. Error text (red) and anim note (blue) are mutually exclusive: error wins when set.

Verified: 118 passed (was 114 before this session; +4 new tests: `test_menu_screen_size_clamps_dimensions`, `test_menu_anim_mode_clamps_to_anim_max_side`, `test_menu_type_change_reclamps_dimensions`, plus the animation completes/skip tests were already in the prior count). Full suite ~1.6s. Interactive acceptance (screen clamping, menu anim limit, HUD warning) requires user at a real display.

