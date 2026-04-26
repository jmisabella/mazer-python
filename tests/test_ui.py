"""Renderer smoke tests under the SDL ``dummy`` video driver.

These don't try to validate pixel-level output (that's what the iOS
visual reference is for, and pixel diffs are notoriously brittle). They
prove the renderers can be constructed against a real maze and a real
Pygame surface and run ``draw()`` end-to-end without exceptions, with a
cheap "did *something* get drawn" sanity check on the resulting surface.

Why ``SDL_VIDEODRIVER=dummy``: pygame's font + draw subsystems all need
``pygame.init()`` to have run, which on headless macOS/Linux CI would try
to open a real window. The dummy driver gives us the same APIs writing
into an in-memory surface — it's the same approach the Stage 4 smoke
test used.
"""

from __future__ import annotations

import os

import pygame
import pytest

from mazer.maze import Maze
from mazer.types import Algorithm, Coord, MazeRequest, MazeType


@pytest.fixture(scope="module", autouse=True)
def _pygame_dummy():
    """Initialize pygame with the dummy SDL driver for the whole module.

    Set the env var *before* ``pygame.init()`` and tear down on teardown.
    Module scope (rather than function) avoids paying init/quit per test.
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    yield
    pygame.quit()


def _surface_has_content(surface: pygame.Surface) -> bool:
    """Check at least two distinct colors got painted on the surface.

    A renderer that silently no-ops leaves a uniform-color surface. Any
    real draw call paints a fill, walls in a different color, plus
    markers — so a coarse sample over a 2-D grid of pixels should hit at
    least two colors. We sample a grid (rather than one row) so the
    check works regardless of where the renderer placed the maze inside
    the surface.
    """
    w, h = surface.get_size()
    colors = {
        surface.get_at((x, y))[:3]
        for y in range(0, h, max(1, h // 16))
        for x in range(0, w, max(1, w // 16))
    }
    return len(colors) > 1


def test_orthogonal_renderer_draws_without_error() -> None:
    from mazer.ui.renderer import OrthogonalRenderer

    surface = pygame.Surface((200, 200))
    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5,
        height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(4, 4),
    )
    with Maze(request) as m:
        renderer = OrthogonalRenderer(surface, cell_size=20)
        renderer.draw(m.cells(), show_heatmap=True, show_solution=True)
    assert _surface_has_content(surface)


def test_sigma_renderer_draws_without_error() -> None:
    """A small sigma maze should render walls + cells + markers cleanly."""
    from mazer.ui.renderer import SigmaRenderer

    surface = pygame.Surface((400, 400))
    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=5,
        height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(4, 4),
    )
    with Maze(request) as m:
        renderer = SigmaRenderer(surface, cell_size=24)
        renderer.draw(m.cells(), show_heatmap=False, show_solution=False)
        # Toggle both overlays in a second pass to exercise the heatmap +
        # solution branches of cell_color.
        renderer.draw(m.cells(), show_heatmap=True, show_solution=True)
    assert _surface_has_content(surface)


def test_make_renderer_dispatch() -> None:
    """The factory returns a renderer matching the maze type, or raises."""
    from mazer.ui.renderer import OrthogonalRenderer, SigmaRenderer, make_renderer

    surface = pygame.Surface((100, 100))
    assert isinstance(make_renderer(MazeType.ORTHOGONAL, surface, 20), OrthogonalRenderer)
    assert isinstance(make_renderer(MazeType.SIGMA, surface, 20), SigmaRenderer)
    with pytest.raises(NotImplementedError):
        make_renderer(MazeType.DELTA, surface, 20)


# --- Chord arrow resolver -------------------------------------------------

@pytest.mark.parametrize(
    "up,down,left,right,expected",
    [
        # Single-arrow cardinals.
        (True, False, False, False, "Up"),
        (False, True, False, False, "Down"),
        (False, False, True, False, "Left"),
        (False, False, False, True, "Right"),
        # Diagonal chords.
        (True, False, False, True, "UpperRight"),
        (True, False, True, False, "UpperLeft"),
        (False, True, False, True, "LowerRight"),
        (False, True, True, False, "LowerLeft"),
        # Opposing-axis cancels: UP+DOWN cancels vertical, RIGHT remains.
        (True, True, False, True, "Right"),
        (True, True, True, False, "Left"),
        # LEFT+RIGHT cancels horizontal, UP remains.
        (True, False, True, True, "Up"),
        (False, True, True, True, "Down"),
        # Both axes cancel — nothing meaningful to fire.
        (True, True, True, True, None),
        # Nothing held — None (defensive; KEYDOWN should never reach this).
        (False, False, False, False, None),
    ],
)
def test_resolve_chord_matrix(up, down, left, right, expected) -> None:
    """Held-arrow combinations resolve to the right Direction."""
    from mazer.types import Direction
    from mazer.ui.app import _resolve_chord

    result = _resolve_chord(up, down, left, right)
    if expected is None:
        assert result is None
    else:
        assert result == Direction(expected)


# --- Hit-test ------------------------------------------------------------

def test_orthogonal_cell_at_resolves_clicks() -> None:
    """Click coords inside the orthogonal grid map back to the right cell."""
    from mazer.ui.renderer import OrthogonalRenderer
    from mazer.types import Coord

    surface = pygame.Surface((200, 200))
    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=4,
        height=4,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(3, 3),
    )
    cell_size = 25
    offset = (10, 30)
    renderer = OrthogonalRenderer(surface, cell_size=cell_size, offset=offset)
    with Maze(request) as m:
        cells = m.cells()
        # Click in the dead-center of (2, 1).
        center = (offset[0] + 2 * cell_size + cell_size // 2,
                  offset[1] + 1 * cell_size + cell_size // 2)
        assert renderer.cell_at(center, cells) == Coord(2, 1)
        # A click in the HUD area (above offset_y) should resolve to None.
        assert renderer.cell_at((offset[0] + 5, 5), cells) is None
        # A click well to the right of the maze should resolve to None.
        assert renderer.cell_at((offset[0] + cell_size * 10, offset[1] + 5), cells) is None


def test_sigma_cell_at_resolves_clicks() -> None:
    """Sigma point-in-polygon hit-test lands on the cell the click is inside."""
    from mazer.ui.renderer import SigmaRenderer
    from mazer.types import Coord

    surface = pygame.Surface((400, 400))
    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=4,
        height=4,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(3, 3),
    )
    renderer = SigmaRenderer(surface, cell_size=24, offset=(10, 30))
    with Maze(request) as m:
        cells = m.cells()
        # Click on each cell's exact center → must resolve to that cell.
        for cell in cells:
            cx, cy = renderer._cell_center(cell.coord.x, cell.coord.y)
            assert renderer.cell_at((int(cx), int(cy)), cells) == cell.coord, (
                f"center of {cell.coord} resolved wrong"
            )
        # Click in the HUD area (above offset_y) should resolve to None.
        assert renderer.cell_at((20, 5), cells) is None


# --- Direction lookup ----------------------------------------------------

def test_orthogonal_direction_lookup() -> None:
    from mazer.types import Coord, Direction
    from mazer.ui.renderer import orthogonal_direction

    assert orthogonal_direction(Coord(2, 2), Coord(2, 1)) == Direction.UP
    assert orthogonal_direction(Coord(2, 2), Coord(2, 3)) == Direction.DOWN
    assert orthogonal_direction(Coord(2, 2), Coord(1, 2)) == Direction.LEFT
    assert orthogonal_direction(Coord(2, 2), Coord(3, 2)) == Direction.RIGHT
    # Non-adjacent or diagonal returns None.
    assert orthogonal_direction(Coord(2, 2), Coord(3, 3)) is None
    assert orthogonal_direction(Coord(2, 2), Coord(2, 4)) is None
    assert orthogonal_direction(Coord(2, 2), Coord(2, 2)) is None


def test_sigma_direction_lookup_returns_linked_name() -> None:
    """For every direction in a cell's ``linked`` set, the lookup recovers it.

    Drives the test from each (cell, direction-in-linked) pair so we cover
    the boundary-clamp asymmetry: at a top-row even-col cell the FFI may
    keep only one of (UpperRight/LowerRight) in ``linked``, but whichever
    name is there should round-trip cleanly through ``sigma_direction``.
    """
    from mazer.types import Coord
    from mazer.ui.renderer import hex_candidate_deltas, sigma_direction

    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=5,
        height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(4, 4),
    )
    with Maze(request) as m:
        cells = m.cells()
        by_coord = {c.coord: c for c in cells}
        height = max(c.coord.y for c in cells) + 1
        for cell in cells:
            for direction in cell.linked:
                # Resolve the geometric target via the same candidate-deltas
                # path the renderer uses.
                target: Coord | None = None
                for dx, dy in hex_candidate_deltas(
                    direction, cell.coord.x, cell.coord.y, height
                ):
                    candidate = Coord(cell.coord.x + dx, cell.coord.y + dy)
                    if candidate in by_coord:
                        target = candidate
                        break
                assert target is not None, (
                    f"linked direction {direction} from {cell.coord} doesn't reach any cell"
                )
                returned = sigma_direction(cell, target, cells)
                assert returned is not None
                assert returned in cell.linked
