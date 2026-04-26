
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


