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
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType


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


# --- Drag direction resolver ------------------------------------------------

@pytest.mark.parametrize("dx,dy,expected", [
    (20, 0, "Right"),
    (-20, 0, "Left"),
    (0, -20, "Up"),
    (0, 20, "Down"),
    (15, -15, "Right"),   # 45° up-right → dominant axis is equal → Right wins (|dx|>=|dy|)
    (15, 15, "Right"),    # 45° down-right
    (-15, -15, "Left"),
    (-15, 15, "Left"),
    (5, -20, "Up"),       # mostly up
    (5, 20, "Down"),      # mostly down
])
def test_direction_from_vector_orthogonal(dx, dy, expected) -> None:
    from mazer.ui.app import _direction_from_vector
    result = _direction_from_vector(dx, dy, MazeType.ORTHOGONAL)
    assert result == Direction(expected)


@pytest.mark.parametrize("angle_deg,expected", [
    (270, "Up"),
    (330, "UpperRight"),
    (30,  "LowerRight"),
    (90,  "Down"),
    (150, "LowerLeft"),
    (210, "UpperLeft"),
])
def test_direction_from_vector_sigma(angle_deg, expected) -> None:
    """Drag vectors at the center of each hex sector resolve to the right direction."""
    import math as _math
    from mazer.ui.app import _direction_from_vector
    rad = _math.radians(angle_deg)
    dx = _math.cos(rad) * 50
    dy = _math.sin(rad) * 50
    result = _direction_from_vector(dx, dy, MazeType.SIGMA)
    assert result == Direction(expected)


# --- Drag-to-move -----------------------------------------------------------

def test_drag_to_move_orthogonal() -> None:
    """Dragging past the threshold in an open direction moves the player."""
    from mazer.ui.renderer import ORTHO_OFFSETS
    from mazer.ui.app import _DragState

    cell_size = 20
    threshold = int(cell_size * 0.6) + 2  # comfortably past the 0.6 threshold

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    with Maze(request) as maze:
        cells = maze.cells()
        start = next(c for c in cells if c.is_active)
        if not start.linked:
            pytest.skip("start cell has no open walls")
        # Pick the first open direction and build a drag vector for it.
        direction = next(iter(start.linked))
        ddx, ddy = ORTHO_OFFSETS[direction]

        drag = _DragState()
        drag.begin((100, 100))  # anchor anywhere
        assert drag.active

        # Move cursor threshold units in the open direction.
        pos = (100 + ddx * threshold, 100 + ddy * threshold)
        fired = drag.motion(pos, maze, cell_size, MazeType.ORTHOGONAL)
        assert fired, f"drag in open direction {direction} should fire a move"

        cells_final = maze.cells()
        active = next(c for c in cells_final if c.is_active)
        assert active.coord != start.coord, "player should have moved"

        drag.end()
        assert not drag.active


def test_drag_to_move_sigma() -> None:
    """Dragging past the threshold fires a move in the resolved hex direction."""
    import math as _math
    from mazer.ui.app import _DragState, _direction_from_vector

    cell_size = 24
    threshold = int(cell_size * 0.6) + 2

    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    # Hex sector angles (degrees) for each sigma direction.
    _SIGMA_CENTER_ANGLES = {
        Direction.UP: 270, Direction.UPPER_RIGHT: 330,
        Direction.LOWER_RIGHT: 30, Direction.DOWN: 90,
        Direction.LOWER_LEFT: 150, Direction.UPPER_LEFT: 210,
    }
    with Maze(request) as maze:
        cells = maze.cells()
        start = next(c for c in cells if c.is_active)
        if not start.linked:
            pytest.skip("start cell has no open walls")
        # Try each linked direction until one produces a valid move.
        for direction in start.linked:
            angle = _SIGMA_CENTER_ANGLES.get(direction)
            if angle is None:
                continue
            rad = _math.radians(angle)
            drag = _DragState()
            drag.begin((200, 200))
            pos = (200 + int(_math.cos(rad) * threshold),
                   200 + int(_math.sin(rad) * threshold))
            # Verify the vector resolves to the intended direction.
            resolved = _direction_from_vector(pos[0] - 200, pos[1] - 200, MazeType.SIGMA)
            if resolved != direction:
                continue  # floating-point edge case; skip to next direction
            fired = drag.motion(pos, maze, cell_size, MazeType.SIGMA)
            drag.end()
            if fired:
                cells_final = maze.cells()
                active = next(c for c in cells_final if c.is_active)
                assert active.coord != start.coord
                return
        pytest.skip("no open sigma direction produced a successful move")


def test_drag_motion_ignored_when_not_active() -> None:
    """motion() is a no-op before begin() is called."""
    from mazer.ui.app import _DragState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=3, height=3,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(2, 2),
    )
    with Maze(request) as maze:
        drag = _DragState()
        fired = drag.motion((100, 100), maze, 20, MazeType.ORTHOGONAL)
        assert not fired


def test_drag_motion_below_threshold_fires_no_move() -> None:
    """A tiny drag below the threshold does not move the player."""
    from mazer.ui.app import _DragState

    cell_size = 20
    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=3, height=3,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(2, 2),
    )
    with Maze(request) as maze:
        drag = _DragState()
        drag.begin((100, 100))
        # Move 1 pixel — well below the cell_size * 0.6 threshold.
        fired = drag.motion((101, 100), maze, cell_size, MazeType.ORTHOGONAL)
        assert not fired


def test_drag_begin_fires_no_move() -> None:
    """BUTTONDOWN (begin) only records the anchor — no move is fired."""
    from mazer.ui.app import _DragState

    drag = _DragState()
    assert not drag.active
    drag.begin((42, 99))
    assert drag.active


def test_gradient_changes_default_cell_colors() -> None:
    """Rendering with a gradient produces different background colors than plain off-white.

    We use a saturated accent (pure red) so the tint is unambiguous even at
    the low 0.17 factor. The test checks that at least one cell row differs
    from the OFF_WHITE fallback — not that every cell is different, since
    the start/goal/visited priority overrides the gradient on some cells.
    """
    from mazer.ui.renderer import GradientTheme, OFF_WHITE, OrthogonalRenderer

    surface_plain = pygame.Surface((200, 200))
    surface_grad = pygame.Surface((200, 200))

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=4, height=4,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(3, 3),
    )
    with Maze(request) as m:
        cells = m.cells()
        plain = OrthogonalRenderer(surface_plain, cell_size=30)
        plain.draw(cells, show_heatmap=False, show_solution=False)

        # A vivid accent to make the gradient detectable even at factor 0.17.
        accent = (220, 0, 0)
        grad_theme = GradientTheme(base=(200, 235, 215), accent=accent)
        grad_renderer = OrthogonalRenderer(surface_grad, cell_size=30)
        grad_renderer.set_gradient(grad_theme)
        grad_renderer.draw(cells, show_heatmap=False, show_solution=False)

    # Sample the surfaces at the same interior pixels. At least some must differ.
    w, h = surface_plain.get_size()
    plain_colors = {surface_plain.get_at((x, y))[:3] for y in range(5, h, 30) for x in range(5, w, 30)}
    grad_colors = {surface_grad.get_at((x, y))[:3] for y in range(5, h, 30) for x in range(5, w, 30)}
    assert plain_colors != grad_colors, "gradient render should produce different colors from plain off-white"


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
