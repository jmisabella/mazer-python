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
