"""End-to-end integration tests covering the FFI → wrapper → game-logic stack.

These exercises sit one rung above ``test_maze.py``: that file proves each
``Maze`` method behaves in isolation; this file proves they compose into a
working game without touching Pygame. Every test runs against the real
Rust library through cffi.

The Orthogonal direction-to-coord-offset map is duplicated here (it also
lives implicitly in the Rust library) because we need it to walk the
solution path: ``cell.linked`` tells us which walls are open, but to
discover *which neighbor cell that opens onto* we have to translate the
direction back into a coordinate delta. Convention confirmed against the
existing ``test_maze.py`` reasoning that at ``(0,0)`` both ``UP`` and
``LEFT`` are off-grid: UP = ``y-1``, LEFT = ``x-1``.
"""

from __future__ import annotations

import pytest

from mazer.maze import Cell, Maze
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType


_ORTHOGONAL_OFFSETS: dict[Direction, tuple[int, int]] = {
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}


def _sigma_candidate_deltas(
    direction: Direction, col: int, row: int, height: int
) -> list[tuple[int, int]]:
    """All offsets a sigma direction *could* refer to from a given cell.

    Inlined here rather than imported from ``mazer.ui.renderer`` so the
    test file stays free of pygame imports. See the renderer module for
    the explanation; in short, the Rust library's ``set_open_walls`` (in
    ``cell.rs``) keeps only the first matching direction name when two
    HashMap entries point to the same neighbor. The collision only
    happens on boundary rows (top for even cols, bottom for odd cols)
    where ``assign_neighbors_sigma`` clamps to avoid underflow/overflow.

    Adding the clamp variant unconditionally was a real bug: at
    non-boundary cells the alternate offset points to a *different*
    physical neighbor that happens to share neither side's direction
    name, so the picker would think a forward move existed when the
    Rust-side ``move`` actually lands somewhere else.
    """
    is_odd = (col & 1) == 1
    if direction == Direction.UP:
        return [(0, -1)]
    if direction == Direction.DOWN:
        return [(0, 1)]
    standard: tuple[int, int] | None = None
    if is_odd:
        if direction == Direction.UPPER_LEFT:
            standard = (-1, 0)
        elif direction == Direction.UPPER_RIGHT:
            standard = (1, 0)
        elif direction == Direction.LOWER_LEFT:
            standard = (-1, 1)
        elif direction == Direction.LOWER_RIGHT:
            standard = (1, 1)
    else:
        if direction == Direction.UPPER_LEFT:
            standard = (-1, -1)
        elif direction == Direction.UPPER_RIGHT:
            standard = (1, -1)
        elif direction == Direction.LOWER_LEFT:
            standard = (-1, 0)
        elif direction == Direction.LOWER_RIGHT:
            standard = (1, 0)
    if standard is None:
        return []
    candidates = [standard]
    on_top_even_edge = not is_odd and row == 0
    on_bottom_odd_edge = is_odd and row == height - 1
    if direction in (Direction.UPPER_LEFT, Direction.UPPER_RIGHT) and on_top_even_edge:
        candidates.append((standard[0], 0))
    elif direction in (Direction.LOWER_LEFT, Direction.LOWER_RIGHT) and on_bottom_odd_edge:
        candidates.append((standard[0], 0))
    return candidates


def _by_coord(cells: list[Cell]) -> dict[Coord, Cell]:
    return {c.coord: c for c in cells}


def _active(cells: list[Cell]) -> Cell:
    return next(c for c in cells if c.is_active)


def _start(cells: list[Cell]) -> Cell:
    return next(c for c in cells if c.is_start)


def _solution_path_reaches_goal(cells: list[Cell]) -> bool:
    """BFS through ``on_solution_path`` cells, following only ``linked`` edges.

    Returns True iff a goal cell is reachable from the start cell while
    staying on the solution path the Rust side computed. This is stricter
    than "start and goal both have ``on_solution_path=True``" because it
    catches a (hypothetical) bug where the flag is set on disconnected
    cells: the path must actually be a connected chain.
    """
    by_coord = _by_coord(cells)
    start = _start(cells)
    if not start.on_solution_path:
        return False
    queue: list[Cell] = [start]
    visited: set[Coord] = {start.coord}
    while queue:
        cell = queue.pop(0)
        if cell.is_goal:
            return True
        for direction in cell.linked:
            offset = _ORTHOGONAL_OFFSETS.get(direction)
            if offset is None:
                continue
            dx, dy = offset
            target = Coord(cell.coord.x + dx, cell.coord.y + dy)
            if target in visited:
                continue
            neighbor = by_coord.get(target)
            if neighbor is not None and neighbor.on_solution_path:
                visited.add(target)
                queue.append(neighbor)
    return False


def test_solve_maze_by_following_solution_path() -> None:
    """Walk the active cell along ``on_solution_path`` from start to goal.

    At each step we look at the active cell's open directions and pick the
    one whose neighbor is on the solution path and hasn't been visited
    yet. In a perfect maze the solution path is a simple chain, so there's
    always exactly one such direction except at the start (where any
    branch direction off the path is excluded by ``on_solution_path`` and
    the goal terminates the loop).

    A ``max_steps`` guard bounds the loop at width*height to fail loudly
    rather than hang if the invariants above ever break.
    """
    width, height = 8, 8
    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=width,
        height=height,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(width - 1, height - 1),
    )

    with Maze(request) as m:
        visited: set[Coord] = set()
        max_steps = width * height
        for _ in range(max_steps):
            cells = m.cells()
            active = _active(cells)
            visited.add(active.coord)
            if active.is_goal:
                break
            by_coord = _by_coord(cells)
            next_direction: Direction | None = None
            for direction in active.linked:
                offset = _ORTHOGONAL_OFFSETS.get(direction)
                if offset is None:
                    continue
                dx, dy = offset
                target = Coord(active.coord.x + dx, active.coord.y + dy)
                neighbor = by_coord.get(target)
                if (
                    neighbor is not None
                    and neighbor.on_solution_path
                    and target not in visited
                ):
                    next_direction = direction
                    break
            assert next_direction is not None, (
                f"no forward solution-path move from {active.coord}; "
                f"linked={active.linked}, visited={visited}"
            )
            assert m.move(next_direction) is True, (
                f"move {next_direction} from {active.coord} unexpectedly rejected"
            )
        else:  # pragma: no cover - guard against an infinite loop on a regression
            pytest.fail(f"did not reach goal within {max_steps} moves")

        final_active = _active(m.cells())
        assert final_active.is_goal
        assert final_active.coord == Coord(width - 1, height - 1)


def test_solve_sigma_maze_by_following_solution_path() -> None:
    """Same path-walk pattern as the Orthogonal solver, but on a hex grid.

    Proves the FFI + wrapper handle hex linkage round-trip end-to-end:
    every linked direction the Rust side reports must also be a valid
    move, and the hex offset deltas the renderer uses must agree with
    the cell coordinates the FFI returns. Six directions instead of four,
    and the odd-q vertical layout means the offset for diagonals depends
    on whether the active column is odd.
    """
    width, height = 8, 8
    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=width,
        height=height,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(width - 1, height - 1),
    )

    with Maze(request) as m:
        visited: set[Coord] = set()
        max_steps = width * height
        for _ in range(max_steps):
            cells = m.cells()
            active = _active(cells)
            visited.add(active.coord)
            if active.is_goal:
                break
            by_coord = _by_coord(cells)
            next_direction: Direction | None = None
            for direction in active.linked:
                for dx, dy in _sigma_candidate_deltas(
                    direction, active.coord.x, active.coord.y, height
                ):
                    target = Coord(active.coord.x + dx, active.coord.y + dy)
                    neighbor = by_coord.get(target)
                    if (
                        neighbor is not None
                        and neighbor.on_solution_path
                        and target not in visited
                    ):
                        next_direction = direction
                        break
                if next_direction is not None:
                    break
            assert next_direction is not None, (
                f"no forward solution-path move from {active.coord}; "
                f"linked={active.linked}, visited={visited}"
            )
            assert m.move(next_direction) is True, (
                f"move {next_direction} from {active.coord} unexpectedly rejected"
            )
        else:  # pragma: no cover - guard against an infinite loop on a regression
            pytest.fail(f"did not reach goal within {max_steps} moves")

        final_active = _active(m.cells())
        assert final_active.is_goal
        assert final_active.coord == Coord(width - 1, height - 1)


def _delta_offset(direction: Direction, col: int, row: int) -> tuple[int, int] | None:
    """Coordinate offset for a delta direction, conditioned on cell orientation.

    Normal cell ((col+row) even — apex up): UpperLeft=(-1,0), UpperRight=(+1,0), Down=(0,+1).
    Inverted cell ((col+row) odd — apex down): LowerLeft=(-1,0), LowerRight=(+1,0), Up=(0,-1).
    Returns None for directions that aren't valid for this orientation.
    """
    is_normal = (col + row) % 2 == 0
    if is_normal:
        return {
            Direction.UPPER_LEFT: (-1, 0),
            Direction.UPPER_RIGHT: (1, 0),
            Direction.DOWN: (0, 1),
        }.get(direction)
    else:
        return {
            Direction.LOWER_LEFT: (-1, 0),
            Direction.LOWER_RIGHT: (1, 0),
            Direction.UP: (0, -1),
        }.get(direction)


def test_solve_delta_maze_by_following_solution_path() -> None:
    """Same path-walk pattern as the Orthogonal and Sigma solver tests, on a triangle grid.

    Delta direction→offset depends on whether the active cell is Normal
    (apex up, even col+row sum) or Inverted (apex down, odd sum).
    Proves the FFI + wrapper handle triangular linkage end-to-end.
    """
    width, height = 10, 8
    request = MazeRequest(
        maze_type=MazeType.DELTA,
        width=width,
        height=height,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(width - 1, height - 1),
    )

    with Maze(request) as m:
        visited: set[Coord] = set()
        max_steps = width * height
        for _ in range(max_steps):
            cells = m.cells()
            active = _active(cells)
            visited.add(active.coord)
            if active.is_goal:
                break
            by_coord = _by_coord(cells)
            next_direction: Direction | None = None
            for direction in active.linked:
                offset = _delta_offset(direction, active.coord.x, active.coord.y)
                if offset is None:
                    continue
                dx, dy = offset
                target = Coord(active.coord.x + dx, active.coord.y + dy)
                neighbor = by_coord.get(target)
                if (
                    neighbor is not None
                    and neighbor.on_solution_path
                    and target not in visited
                ):
                    next_direction = direction
                    break
            assert next_direction is not None, (
                f"no forward solution-path move from {active.coord}; "
                f"linked={active.linked}, visited={visited}"
            )
            assert m.move(next_direction) is True, (
                f"move {next_direction} from {active.coord} unexpectedly rejected"
            )
        else:  # pragma: no cover - guard against an infinite loop on a regression
            pytest.fail(f"did not reach goal within {max_steps} moves")

        final_active = _active(m.cells())
        assert final_active.is_goal
        assert final_active.coord == Coord(width - 1, height - 1)


def test_solve_rhombic_maze_by_following_solution_path() -> None:
    """Same path-walk pattern as the other solver tests, on a diamond grid.

    Rhombic cells only exist at positions where ``(x + y) % 2 == 0``
    (checkerboard pattern).  All four directions are diagonal; the Rust
    exports them user-facing as UpperRight/LowerRight/LowerLeft/UpperLeft.
    Coord offsets:
      UpperRight=(+1,-1), LowerRight=(+1,+1), LowerLeft=(-1,+1), UpperLeft=(-1,-1).
    Proves the FFI + wrapper handle Rhombic linkage end-to-end.
    """
    width, height = 9, 9  # odd × odd → goal=(8,8) satisfies (8+8)%2==0
    request = MazeRequest(
        maze_type=MazeType.RHOMBIC,
        width=width,
        height=height,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(width - 1, height - 1),
    )

    _RHOMBIC_OFFSETS = {
        Direction.UPPER_RIGHT: (1, -1),
        Direction.LOWER_RIGHT: (1, 1),
        Direction.LOWER_LEFT: (-1, 1),
        Direction.UPPER_LEFT: (-1, -1),
    }

    with Maze(request) as m:
        visited: set[Coord] = set()
        max_steps = width * height
        for _ in range(max_steps):
            cells = m.cells()
            active = _active(cells)
            visited.add(active.coord)
            if active.is_goal:
                break
            by_coord = _by_coord(cells)
            next_direction: Direction | None = None
            for direction in active.linked:
                offset = _RHOMBIC_OFFSETS.get(direction)
                if offset is None:
                    continue
                dx, dy = offset
                target = Coord(active.coord.x + dx, active.coord.y + dy)
                neighbor = by_coord.get(target)
                if (
                    neighbor is not None
                    and neighbor.on_solution_path
                    and target not in visited
                ):
                    next_direction = direction
                    break
            assert next_direction is not None, (
                f"no forward solution-path move from {active.coord}; "
                f"linked={active.linked}, visited={visited}"
            )
            assert m.move(next_direction) is True, (
                f"move {next_direction} from {active.coord} unexpectedly rejected"
            )
        else:  # pragma: no cover
            pytest.fail(f"did not reach goal within {max_steps} moves")

        final_active = _active(m.cells())
        assert final_active.is_goal
        assert final_active.coord == Coord(width - 1, height - 1)


@pytest.mark.parametrize("algorithm", list(Algorithm))
def test_multiple_algorithms_all_produce_valid_mazes(algorithm: Algorithm) -> None:
    """Every algorithm produces a solvable Orthogonal maze.

    "Solvable" here means: the start cell has at least one open wall (so
    the player can move at all), and the Rust-computed solution path
    forms a connected chain from start to goal under ``cell.linked``.
    """
    width, height = 8, 8
    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=width,
        height=height,
        algorithm=algorithm,
        start=Coord(0, 0),
        goal=Coord(width - 1, height - 1),
    )

    with Maze(request) as m:
        cells = m.cells()
        assert len(cells) == width * height

        start = _start(cells)
        assert start.linked, f"{algorithm.value}: start has no open walls"

        assert _solution_path_reaches_goal(cells), (
            f"{algorithm.value}: solution path does not connect start to goal"
        )
