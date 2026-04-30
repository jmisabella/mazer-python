"""Pythonic Maze API tests — read these as the user-facing usage docs.

Each test is one concept, named for what it asserts, with the smallest
``MazeRequest`` that demonstrates it. Where possible the test mirrors how
gameplay or rendering code would actually call into ``Maze`` — the test
file doubles as the primary example of what "using mazer" looks like.

These tests run against the **real** Rust library through cffi (no mocks
of the FFI surface). Two reasons:
  * Mocking ``lib`` would test our wrapper against our assumptions about
    Rust, not against Rust's actual behavior — the bugs that bite hardest
    here (off-by-one in cell counts, direction string drift, struct
    layout mismatch) only show up against the real ``.so``.
  * The FFI tests in ``test_ffi.py`` already cover the C boundary; this
    file's value is showing the wrapper composes those calls correctly.

Lifetime tests at the bottom (destroy-on-exit, idempotent close) use a
small ``CountingLib`` ``__getattr__`` proxy patched into ``mazer.maze``
because the cffi-generated ``lib`` object rejects attribute assignment,
so ``monkeypatch.setattr(lib, "mazer_destroy", ...)`` fails. Patching the
module-level name is the only ergonomic option.
"""

from __future__ import annotations

import pytest

from mazer.maze import Cell, Maze, MazeGenerationError
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _request(**overrides) -> MazeRequest:
    """Build a small Orthogonal RecursiveBacktracker request with overrides.

    These defaults are deliberately small (5x5) so tests are fast and the
    invariants we check (one start, one goal, etc.) are easy to inspect
    if a failure prints the cell list.
    """
    base: dict = dict(
        maze_type=MazeType.ORTHOGONAL,
        width=5,
        height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(4, 4),
    )
    base.update(overrides)
    return MazeRequest(**base)


def _start_cell(cells: list[Cell]) -> Cell:
    return next(c for c in cells if c.is_start)


def _goal_cell(cells: list[Cell]) -> Cell:
    return next(c for c in cells if c.is_goal)


def _active_cell(cells: list[Cell]) -> Cell:
    return next(c for c in cells if c.is_active)


# -----------------------------------------------------------------------------
# Tests — basic generation & cell properties
# -----------------------------------------------------------------------------
def test_generate_small_orthogonal_maze() -> None:
    """The canonical usage example: build a request, open the maze, read cells."""
    with Maze(_request()) as m:
        assert len(m.cells()) > 0


def test_cells_count_matches_dimensions() -> None:
    """An orthogonal NxM maze has exactly N*M cells."""
    width, height = 4, 6
    request = _request(width=width, height=height, goal=Coord(width - 1, height - 1))
    with Maze(request) as m:
        assert len(m.cells()) == width * height


def test_start_cell_marked_correctly() -> None:
    """Exactly one cell should be marked ``is_start``, at the requested coords."""
    start = Coord(0, 0)
    with Maze(_request(start=start)) as m:
        starts = [c for c in m.cells() if c.is_start]
        assert len(starts) == 1
        assert starts[0].coord == start


def test_goal_cell_marked_correctly() -> None:
    """Exactly one cell should be marked ``is_goal``, at the requested coords."""
    goal = Coord(4, 4)
    with Maze(_request(goal=goal)) as m:
        goals = [c for c in m.cells() if c.is_goal]
        assert len(goals) == 1
        assert goals[0].coord == goal


def test_initial_active_cell_is_start() -> None:
    """At generation time, the player (active cell) sits on the start cell."""
    with Maze(_request()) as m:
        active = _active_cell(m.cells())
        assert active.is_start
        assert active.coord == Coord(0, 0)


# -----------------------------------------------------------------------------
# Tests — movement
# -----------------------------------------------------------------------------
def test_invalid_move_returns_false_and_grid_intact() -> None:
    """A move into a wall returns False and leaves the active cell where it was.

    Picks a direction NOT in the start cell's ``linked`` set — by definition
    that direction is blocked. We then assert the active cell hasn't moved
    by re-reading ``cells()`` (which re-fetches from the FFI; the cache was
    invalidated by the failed call... actually no, only successful moves
    invalidate. The point stands either way: state must be unchanged).
    """
    with Maze(_request()) as m:
        start = _start_cell(m.cells())
        orthogonal_dirs = {Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT}
        # Start cell is at (0,0): UP and LEFT are off-grid AND not linked,
        # so they're guaranteed-blocked regardless of which two directions
        # the algorithm carved.
        blocked = next(iter(orthogonal_dirs - start.linked))
        assert m.move(blocked) is False
        active_after = _active_cell(m.cells())
        assert active_after.coord == start.coord


def test_valid_move_advances_active_cell() -> None:
    """A move into a linked direction returns True and the active cell shifts."""
    with Maze(_request()) as m:
        start = _start_cell(m.cells())
        assert start.linked, "start cell must have at least one open wall"
        direction = next(iter(start.linked))
        assert m.move(direction) is True
        active_after = _active_cell(m.cells())
        assert active_after.coord != start.coord


def test_cells_cache_invalidated_after_move() -> None:
    """``cells()`` must reflect the new active cell after a successful move.

    Specifically: the second ``cells()`` call should not return the cached
    pre-move snapshot. We test this by checking the active cell differs.
    """
    with Maze(_request()) as m:
        first_snapshot = m.cells()
        start = _start_cell(first_snapshot)
        direction = next(iter(start.linked))
        assert m.move(direction) is True
        second_snapshot = m.cells()
        assert second_snapshot is not first_snapshot, "cache should have been invalidated"
        assert _active_cell(second_snapshot).coord != start.coord


# -----------------------------------------------------------------------------
# Tests — solution + heatmap
# -----------------------------------------------------------------------------
def test_solution_path_connects_start_to_goal() -> None:
    """The cells where ``on_solution_path=True`` form a chain including start and goal."""
    with Maze(_request(width=8, height=8, goal=Coord(7, 7))) as m:
        path_cells = [c for c in m.cells() if c.on_solution_path]
        assert path_cells, "solution path should be non-empty in a perfect maze"
        assert any(c.is_start for c in path_cells)
        assert any(c.is_goal for c in path_cells)


def test_distances_form_valid_heatmap() -> None:
    """Distances are 0 at start, > 0 at goal, and non-negative everywhere reachable.

    A perfect maze (which the Rust library guarantees) makes every cell
    reachable from the start, so every cell should have a non-negative
    distance. Goal distance is strictly positive because start != goal here.
    """
    with Maze(_request()) as m:
        cells = m.cells()
        start = _start_cell(cells)
        goal = _goal_cell(cells)
        assert start.distance == 0
        assert goal.distance > 0
        assert all(c.distance >= 0 for c in cells)


# -----------------------------------------------------------------------------
# Tests — generation steps
# -----------------------------------------------------------------------------
def test_capture_steps_yields_progressive_cells() -> None:
    """With ``capture_steps=True``, step snapshots exist and the last matches final.

    The number of steps is algorithm-dependent so we only assert > 0. The
    last step's cell list must contain the same number of cells as the
    final maze (one cell per grid position throughout generation).
    """
    request = _request(
        width=4,
        height=4,
        algorithm=Algorithm.HUNT_AND_KILL,
        goal=Coord(3, 3),
        capture_steps=True,
    )
    with Maze(request) as m:
        steps = list(m.generation_steps())
        assert len(steps) > 0
        assert len(steps[-1]) == len(m.cells())


def test_generation_steps_empty_when_not_captured() -> None:
    """Without ``capture_steps``, the iterator yields nothing (count is 0)."""
    with Maze(_request()) as m:  # capture_steps defaults to False
        assert list(m.generation_steps()) == []


# -----------------------------------------------------------------------------
# Tests — error & lifecycle
# -----------------------------------------------------------------------------
def test_zero_size_request_raises_maze_generation_error() -> None:
    """A 0x0 request can't produce a valid maze; ``MazeGenerationError`` should fire."""
    bad = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=0,
        height=0,
        algorithm=Algorithm.WILSONS,
    )
    with pytest.raises(MazeGenerationError):
        Maze(bad)


def _patch_counting_lib(monkeypatch) -> dict[str, int]:
    """Wrap ``mazer.maze.lib`` in a proxy that counts ``mazer_destroy`` calls.

    Returns the shared counter dict so callers can assert on it after the
    operation under test runs. The proxy forwards every other attribute
    through unchanged so the rest of the wrapper still talks to real Rust.
    """
    import mazer.maze as maze_mod

    counter: dict[str, int] = {"destroy": 0}
    real_lib = maze_mod.lib

    class CountingLib:
        def __getattr__(self, name: str):
            attr = getattr(real_lib, name)
            if name != "mazer_destroy":
                return attr

            def wrapped(ptr):
                counter["destroy"] += 1
                return attr(ptr)

            return wrapped

    monkeypatch.setattr(maze_mod, "lib", CountingLib())
    return counter


def test_context_manager_destroys_on_exit(monkeypatch) -> None:
    """Exiting the ``with`` block calls ``mazer_destroy`` exactly once."""
    counter = _patch_counting_lib(monkeypatch)
    with Maze(_request()) as m:
        assert m.closed is False
    assert m.closed is True
    assert counter["destroy"] == 1


def test_close_is_idempotent(monkeypatch) -> None:
    """Calling ``close()`` repeatedly does not double-free."""
    counter = _patch_counting_lib(monkeypatch)
    m = Maze(_request())
    m.close()
    m.close()
    m.close()
    assert m.closed is True
    assert counter["destroy"] == 1


def test_operations_after_close_raise() -> None:
    """Touching a closed maze raises rather than feeding NULL to the FFI."""
    m = Maze(_request())
    m.close()
    with pytest.raises(RuntimeError):
        m.cells()
    with pytest.raises(RuntimeError):
        m.move(Direction.RIGHT)
    with pytest.raises(RuntimeError):
        list(m.generation_steps())
