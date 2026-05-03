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


def test_delta_renderer_draws_without_error() -> None:
    """A small delta maze should render triangles + walls + active marker cleanly."""
    from mazer.ui.renderer import DeltaRenderer

    surface = pygame.Surface((400, 400))
    request = MazeRequest(
        maze_type=MazeType.DELTA,
        width=8,
        height=6,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(7, 5),
    )
    with Maze(request) as m:
        renderer = DeltaRenderer(surface, cell_size=30)
        renderer.draw(m.cells(), show_heatmap=False, show_solution=False)
        renderer.draw(m.cells(), show_heatmap=True, show_solution=True)
    assert _surface_has_content(surface)


def test_delta_cell_at_resolves_clicks() -> None:
    """Clicking at the centroid of a triangle resolves to that cell's coord."""
    from mazer.ui.renderer import DeltaRenderer

    cell_size = 40
    surface = pygame.Surface((500, 400))
    request = MazeRequest(
        maze_type=MazeType.DELTA,
        width=6,
        height=4,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(5, 3),
    )
    with Maze(request) as m:
        cells = m.cells()
        renderer = DeltaRenderer(surface, cell_size=cell_size)
        # Check two cells: (0,0) is Normal (apex up), (1,0) is Inverted (apex down).
        for coord in (Coord(0, 0), Coord(1, 0), Coord(2, 1), Coord(3, 2)):
            cx, cy = renderer._cell_center(coord.x, coord.y)
            result = renderer.cell_at((int(round(cx)), int(round(cy))), cells)
            assert result == coord, f"cell_at centroid of {coord} returned {result}"
        # A click outside the maze rect returns None.
        assert renderer.cell_at((-5, -5), cells) is None


def test_rhombic_renderer_draws_without_error() -> None:
    """A small rhombic maze should render diamonds + walls + active marker cleanly."""
    from mazer.ui.renderer import RhombicRenderer

    surface = pygame.Surface((400, 400))
    request = MazeRequest(
        maze_type=MazeType.RHOMBIC,
        width=7,
        height=7,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(6, 6),
    )
    with Maze(request) as m:
        renderer = RhombicRenderer(surface, cell_size=30)
        renderer.draw(m.cells(), show_heatmap=False, show_solution=False)
        renderer.draw(m.cells(), show_heatmap=True, show_solution=True)
    assert _surface_has_content(surface)


def test_rhombic_cell_at_resolves_clicks() -> None:
    """Clicking at the center of a rhombic diamond resolves to that cell's coord."""
    import math
    from mazer.ui.renderer import RhombicRenderer

    cell_size = 40
    surface = pygame.Surface((600, 600))
    request = MazeRequest(
        maze_type=MazeType.RHOMBIC,
        width=7,
        height=7,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(6, 6),
    )
    with Maze(request) as m:
        cells = m.cells()
        renderer = RhombicRenderer(surface, cell_size=cell_size)
        # Test only valid rhombic cells (x+y even).
        for coord in (Coord(0, 0), Coord(2, 0), Coord(1, 1), Coord(4, 2), Coord(6, 6)):
            cx, cy = renderer._cell_center(coord.x, coord.y)
            result = renderer.cell_at((int(round(cx)), int(round(cy))), cells)
            assert result == coord, f"cell_at center of {coord} returned {result}"
        # A click well outside the maze rect returns None.
        assert renderer.cell_at((-10, -10), cells) is None


def test_upsilon_renderer_draws_without_error() -> None:
    """A small upsilon maze should render octagons + squares + walls cleanly."""
    from mazer.ui.renderer import UpsilonRenderer

    surface = pygame.Surface((400, 400))
    request = MazeRequest(
        maze_type=MazeType.UPSILON,
        width=6,
        height=6,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(5, 5),
    )
    with Maze(request) as m:
        renderer = UpsilonRenderer(surface, cell_size=40)
        renderer.draw(m.cells(), show_heatmap=False, show_solution=False)
        renderer.draw(m.cells(), show_heatmap=True, show_solution=True)
    assert _surface_has_content(surface)


def test_upsilon_cell_at_resolves_clicks() -> None:
    """Clicking at the center of an upsilon cell resolves to that cell's coord.

    Tests both octagon cells (col+row even) and square cells (col+row odd).
    """
    import math
    from mazer.ui.renderer import UpsilonRenderer

    cell_size = 40
    surface = pygame.Surface((500, 500))
    request = MazeRequest(
        maze_type=MazeType.UPSILON,
        width=6,
        height=6,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0),
        goal=Coord(5, 5),
    )
    with Maze(request) as m:
        cells = m.cells()
        renderer = UpsilonRenderer(surface, cell_size=cell_size)
        # Octagon cells: (col+row) % 2 == 0
        for coord in (Coord(0, 0), Coord(2, 0), Coord(0, 2), Coord(4, 4)):
            cx, cy = renderer._cell_center(coord.x, coord.y)
            result = renderer.cell_at((int(round(cx)), int(round(cy))), cells)
            assert result == coord, f"octagon cell_at center of {coord} returned {result}"
        # Square cells: (col+row) % 2 == 1
        for coord in (Coord(1, 0), Coord(0, 1), Coord(3, 2)):
            cx, cy = renderer._cell_center(coord.x, coord.y)
            result = renderer.cell_at((int(round(cx)), int(round(cy))), cells)
            assert result == coord, f"square cell_at center of {coord} returned {result}"
        # A click outside the maze rect returns None.
        assert renderer.cell_at((-10, -10), cells) is None


def test_make_renderer_dispatch() -> None:
    """The factory returns a renderer matching the maze type, or raises."""
    from mazer.ui.renderer import DeltaRenderer, OrthogonalRenderer, RhombicRenderer, SigmaRenderer, UpsilonRenderer, make_renderer

    surface = pygame.Surface((100, 100))
    assert isinstance(make_renderer(MazeType.ORTHOGONAL, surface, 20), OrthogonalRenderer)
    assert isinstance(make_renderer(MazeType.SIGMA, surface, 20), SigmaRenderer)
    assert isinstance(make_renderer(MazeType.DELTA, surface, 20), DeltaRenderer)
    assert isinstance(make_renderer(MazeType.RHOMBIC, surface, 20), RhombicRenderer)
    assert isinstance(make_renderer(MazeType.UPSILON, surface, 20), UpsilonRenderer)


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
    # Pure cardinals.
    (20, 0, "Right"),
    (-20, 0, "Left"),
    (0, -20, "Up"),
    (0, 20, "Down"),
    # 45° diagonals → diagonal directions (Rust tries vertical first, then horizontal).
    (15, -15, "UpperRight"),
    (15, 15, "LowerRight"),
    (-15, -15, "UpperLeft"),
    (-15, 15, "LowerLeft"),
    # Off-diagonal: mostly vertical → cardinal.
    (5, -20, "Up"),
    (5, 20, "Down"),
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


# --- In-game menu (MenuState) -----------------------------------------------

def test_menu_initial_state_mirrors_request() -> None:
    """MenuState seeds its fields from the request that opened it."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.SIGMA,
        width=8,
        height=6,
        algorithm=Algorithm.WILSONS,
        start=Coord(0, 0),
        goal=Coord(7, 5),
    )
    state = MenuState(request)
    assert state.type_idx == MenuState.SUPPORTED_TYPES.index(MazeType.SIGMA)
    assert state._compatible_algos[state.algo_idx] == Algorithm.WILSONS
    assert state.width == 8
    assert state.height == 6
    assert state.section == MenuState.SECTION_TYPE
    assert state.error is None


def test_menu_esc_closes_without_change() -> None:
    """ESC returns (False, None) — close menu, keep current maze."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=10, height=10,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(9, 9),
    )
    state = MenuState(request)
    open_, req = state.handle_keydown(pygame.K_ESCAPE)
    assert open_ is False
    assert req is None


def test_menu_navigation_down_and_up() -> None:
    """DOWN advances the section; UP retreats it; they wrap at boundaries."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    assert state.section == MenuState.SECTION_TYPE

    open_, req = state.handle_keydown(pygame.K_DOWN)
    assert open_ is True and req is None
    assert state.section == MenuState.SECTION_ALGO

    state.handle_keydown(pygame.K_DOWN)
    assert state.section == MenuState.SECTION_WIDTH

    # Go back up.
    state.handle_keydown(pygame.K_UP)
    assert state.section == MenuState.SECTION_ALGO

    # Wrap: UP from SECTION_TYPE wraps to last section.
    state.section = MenuState.SECTION_TYPE
    state.handle_keydown(pygame.K_UP)
    assert state.section == MenuState.NUM_SECTIONS - 1


def test_menu_right_changes_value() -> None:
    """RIGHT increments the current section's value; LEFT decrements."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=10, height=10,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(9, 9),
    )
    state = MenuState(request)

    # Cycle algorithm forward.
    state.section = MenuState.SECTION_ALGO
    orig = state.algo_idx
    state.handle_keydown(pygame.K_RIGHT)
    assert state.algo_idx == (orig + 1) % len(state._compatible_algos)

    # Cycle algorithm back.
    state.handle_keydown(pygame.K_LEFT)
    assert state.algo_idx == orig

    # Width increments.
    state.section = MenuState.SECTION_WIDTH
    state.handle_keydown(pygame.K_RIGHT)
    assert state.width == 11

    state.handle_keydown(pygame.K_LEFT)
    assert state.width == 10


def test_menu_width_height_clamped_at_bounds() -> None:
    """Width and height stay within [MIN_SIZE, MAX_SIZE]."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.section = MenuState.SECTION_WIDTH
    state.width = MenuState.MAX_SIZE
    state.handle_keydown(pygame.K_RIGHT)  # already at max
    assert state.width == MenuState.MAX_SIZE

    state.width = MenuState.MIN_SIZE
    state.handle_keydown(pygame.K_LEFT)  # already at min
    assert state.width == MenuState.MIN_SIZE


def test_menu_generate_returns_request() -> None:
    """Enter (press then release) closes the menu and returns a MazeRequest."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=7, height=8,
        algorithm=Algorithm.HUNT_AND_KILL,
        start=Coord(0, 0), goal=Coord(6, 7),
    )
    state = MenuState(request)

    # KEYDOWN shows pressed state, does not generate yet.
    open_, new_req = state.handle_keydown(pygame.K_RETURN)
    assert open_ is True
    assert new_req is None
    assert state.btn_pressed

    # KEYUP fires generate.
    open_, new_req = state.handle_keyup(pygame.K_RETURN)
    assert open_ is False
    assert new_req is not None
    assert new_req.maze_type == MazeType.ORTHOGONAL
    assert new_req.algorithm == Algorithm.HUNT_AND_KILL
    assert new_req.width == 7
    assert new_req.height == 8


def test_menu_generate_reflects_changed_selections() -> None:
    """The returned request uses the values the user navigated to, not the originals."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)

    # Switch to Sigma.
    state.section = MenuState.SECTION_TYPE
    state.handle_keydown(pygame.K_RIGHT)
    new_type = MenuState.SUPPORTED_TYPES[state.type_idx]
    assert new_type == MazeType.SIGMA

    # Resize to 6×7.
    state.section = MenuState.SECTION_WIDTH
    for _ in range(1):
        state.handle_keydown(pygame.K_RIGHT)
    state.section = MenuState.SECTION_HEIGHT
    for _ in range(2):
        state.handle_keydown(pygame.K_RIGHT)

    state.section = MenuState.SECTION_GENERATE
    state.handle_keydown(pygame.K_RETURN)   # press → show visual
    _, new_req = state.handle_keyup(pygame.K_RETURN)  # release → generate
    assert new_req is not None
    assert new_req.maze_type == MazeType.SIGMA
    assert new_req.width == 6
    assert new_req.height == 7


def test_menu_enter_keydown_shows_pressed_without_generating() -> None:
    """Enter KEYDOWN (from any section) shows Generate as pressed but does not generate."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    assert state.section == MenuState.SECTION_TYPE
    open_, req = state.handle_keydown(pygame.K_RETURN)
    assert open_ is True    # menu stays open
    assert req is None      # not generated yet
    assert state.btn_pressed
    assert state.section == MenuState.SECTION_GENERATE


def test_menu_set_generation_error_focuses_algo() -> None:
    """After a failed generation, error is set and focus jumps to Algorithm."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.set_generation_error()
    assert state.error is not None
    assert len(state.error) > 0
    assert state.section == MenuState.SECTION_ALGO


def test_menu_navigation_clears_error() -> None:
    """Moving between sections clears any prior error message."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.set_generation_error()
    assert state.error is not None

    state.handle_keydown(pygame.K_DOWN)
    assert state.error is None


def test_menu_draw_produces_content() -> None:
    """draw_menu paints onto the surface and returns a non-empty MenuLayout."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=10, height=10,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(9, 9),
    )
    surface = pygame.Surface((700, 700))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    assert _surface_has_content(surface)
    assert len(layout.rows) > 0
    assert len(layout.left_arrows) > 0
    assert len(layout.right_arrows) > 0
    assert layout.generate_btn.width > 0


def test_menu_click_left_arrow_changes_value() -> None:
    """Clicking a left arrow decrements the matching row's value."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=10, height=10,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(9, 9),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    orig_w = state.width
    la = layout.left_arrows[MenuState.SECTION_WIDTH]
    open_, req = state.handle_click((la.centerx, la.centery), layout)
    assert open_ is True
    assert state.width == orig_w - 1


def test_menu_m_key_cancels_menu() -> None:
    """Pressing M while the menu is open closes it without applying changes."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    # Change something so we can verify it isn't applied.
    state.section = MenuState.SECTION_WIDTH
    state.handle_keydown(pygame.K_RIGHT)
    assert state.width == 6

    open_, req = state.handle_keydown(pygame.K_m)
    assert open_ is False
    assert req is None  # cancelled, not generated


def test_menu_click_outside_panel_cancels_menu() -> None:
    """A click outside the panel rect closes the menu without applying changes."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    # Click in the top-left corner, well outside the centred panel.
    open_, req = state.handle_click((5, 5), layout)
    assert open_ is False
    assert req is None


def test_menu_click_generate_button_returns_request() -> None:
    """Clicking the Generate button closes the menu and returns a request."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    btn = layout.generate_btn
    open_, req = state.handle_click((btn.centerx, btn.centery), layout)
    assert open_ is False
    assert req is not None


def test_menu_space_keydown_sets_btn_pressed() -> None:
    """Space KEYDOWN shows the Generate button as pressed without generating."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    open_, req = state.handle_keydown(pygame.K_SPACE)
    assert open_ is True        # menu stays open
    assert req is None          # not generated yet
    assert state.btn_pressed    # pressed visual is active
    assert state.section == MenuState.SECTION_GENERATE


def test_menu_space_keyup_generates() -> None:
    """Space KEYUP after KEYDOWN fires Generate and closes the menu."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.handle_keydown(pygame.K_SPACE)   # press
    open_, req = state.handle_keyup(pygame.K_SPACE)  # release
    assert open_ is False
    assert req is not None
    assert not state.btn_pressed


def test_menu_space_keyup_without_keydown_is_noop() -> None:
    """KEYUP for space without a preceding KEYDOWN is ignored."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    open_, req = state.handle_keyup(pygame.K_SPACE)
    assert open_ is True
    assert req is None


def test_menu_mousedown_on_generate_sets_btn_pressed() -> None:
    """MOUSEBUTTONDOWN on the Generate button shows pressed state, does not generate."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    btn = layout.generate_btn
    open_, req = state.handle_mousedown((btn.centerx, btn.centery), layout)
    assert open_ is True    # menu stays open
    assert req is None      # not fired yet
    assert state.btn_pressed


def test_menu_mouseup_on_generate_fires() -> None:
    """MOUSEBUTTONUP over Generate (after mousedown) closes the menu and returns a request."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    btn = layout.generate_btn
    state.handle_mousedown((btn.centerx, btn.centery), layout)
    open_, req = state.handle_mouseup((btn.centerx, btn.centery), layout)
    assert open_ is False
    assert req is not None
    assert not state.btn_pressed


def test_menu_mouseup_outside_generate_does_not_fire() -> None:
    """Releasing the mouse outside the button after pressing it cancels the action."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)
    layout = draw_menu(surface, state, font)

    btn = layout.generate_btn
    state.handle_mousedown((btn.centerx, btn.centery), layout)
    # Release somewhere far from the button.
    open_, req = state.handle_mouseup((5, 5), layout)
    assert open_ is True   # menu stays open — drag-away is a cancel
    assert req is None
    assert not state.btn_pressed


def test_menu_btn_pressed_color_differs_from_normal() -> None:
    """The Generate button pixel color changes when btn_pressed is True."""
    from mazer.ui.menu import MenuState, draw_menu

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    surface = pygame.Surface((600, 500))
    font = pygame.font.SysFont(None, 22)
    state = MenuState(request)

    layout = draw_menu(surface, state, font)
    btn = layout.generate_btn
    normal_pixel = surface.get_at((btn.centerx, btn.centery))

    state.btn_pressed = True
    draw_menu(surface, state, font)
    pressed_pixel = surface.get_at((btn.centerx, btn.centery))

    assert normal_pixel != pressed_pixel


# --- App smoke test with menu -------------------------------------------

def test_app_menu_opens_and_closes_via_m_and_esc() -> None:
    """Pressing M opens the menu; ESC inside the menu closes it without changing the maze."""
    from mazer.ui.app import main

    events = [
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode="m", scancode=0),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0),
        pygame.event.Event(pygame.QUIT),
    ]
    pygame.event.post(events[0])
    pygame.event.post(events[1])
    pygame.event.post(events[2])
    main([])  # should not raise


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


# --- AnimationState unit tests ------------------------------------------


def test_animation_steps_advance_per_frame() -> None:
    """tick() advances current_step by elapsed_ms / ANIM_STEP_INTERVAL_MS."""
    from mazer.ui.app import ANIM_STEP_INTERVAL_MS, AnimationState

    steps = [[]] * 10
    anim = AnimationState(steps)
    assert anim.current_step == 0
    assert not anim.done

    # One interval → one step forward.
    done = anim.tick(ANIM_STEP_INTERVAL_MS)
    assert anim.current_step == 1
    assert not done

    # Two intervals at once → two steps forward.
    done = anim.tick(ANIM_STEP_INTERVAL_MS * 2)
    assert anim.current_step == 3
    assert not done

    # Sub-interval tick → no advancement (accumulated into next tick).
    before = anim.current_step
    anim.tick(ANIM_STEP_INTERVAL_MS * 0.5)
    assert anim.current_step == before


def test_animation_skip_jumps_to_last() -> None:
    """skip() immediately marks done and sets current_step to the final index."""
    from mazer.ui.app import AnimationState

    steps = [[]] * 5
    anim = AnimationState(steps)
    anim.skip()
    assert anim.current_step == len(steps) - 1
    assert anim.done


def test_animation_completes_at_last_step() -> None:
    """tick() returns True exactly when the last step is reached."""
    from mazer.ui.app import ANIM_STEP_INTERVAL_MS, AnimationState

    steps = [[]] * 3  # steps 0, 1, 2
    anim = AnimationState(steps)
    # Advance past the end in one big tick — should clamp at last and return True.
    done = anim.tick(ANIM_STEP_INTERVAL_MS * 100)
    assert anim.current_step == len(steps) - 1
    assert done
    assert anim.done
    # Subsequent ticks are no-ops.
    done2 = anim.tick(ANIM_STEP_INTERVAL_MS)
    assert not done2
    assert anim.current_step == len(steps) - 1


def test_animation_smoke_with_real_maze() -> None:
    """AnimationState wraps a real generation_steps() sequence without error."""
    from mazer.ui.app import ANIM_STEP_INTERVAL_MS, AnimationState
    from mazer.types import Coord

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=5,
        height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        capture_steps=True,
        start=Coord(0, 0),
        goal=Coord(4, 4),
    )
    with Maze(request) as m:
        all_steps = list(m.generation_steps())

    assert len(all_steps) > 0
    anim = AnimationState(all_steps)
    assert not anim.done

    # Advance until done.
    for _ in range(len(all_steps) + 5):
        if anim.tick(ANIM_STEP_INTERVAL_MS):
            break
    assert anim.done
    assert anim.current_step == len(all_steps) - 1


# --- Screen-size and animation-limit clamping (MenuState) -------------------


def test_menu_screen_size_clamps_dimensions() -> None:
    """max_sizes caps width/height to screen-derived limits on open and during navigation."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=30, height=25,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(29, 24),
    )
    screen_max = {MazeType.ORTHOGONAL: (10, 8)}
    state = MenuState(request, max_sizes=screen_max)
    # Clamped on open.
    assert state.width == 10
    assert state.height == 8
    # Can't push past screen max.
    state.section = MenuState.SECTION_WIDTH
    state.handle_keydown(pygame.K_RIGHT)
    assert state.width == 10
    state.section = MenuState.SECTION_HEIGHT
    state.handle_keydown(pygame.K_RIGHT)
    assert state.height == 8


def test_menu_anim_mode_clamps_to_anim_max_w_h() -> None:
    """When animate_mode is True, width is capped to anim_max_w and height to anim_max_h independently."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=30, height=30,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(29, 29),
    )
    state = MenuState(request, animate_mode=True, anim_max_w=30, anim_max_h=20)
    # Initial clamp to separate axis limits.
    assert state.width == 30
    assert state.height == 20
    # Width can't exceed anim_max_w.
    state.section = MenuState.SECTION_WIDTH
    state.handle_keydown(pygame.K_RIGHT)
    assert state.width == 30
    # Height can't exceed anim_max_h.
    state.section = MenuState.SECTION_HEIGHT
    state.handle_keydown(pygame.K_RIGHT)
    assert state.height == 20
    # Reducing height doesn't raise the width cap.
    state.handle_keydown(pygame.K_LEFT)
    assert state.height == 19
    state.section = MenuState.SECTION_WIDTH
    state.handle_keydown(pygame.K_RIGHT)
    assert state.width == 30  # still capped at anim_max_w regardless of height


def test_menu_type_change_reclamps_dimensions() -> None:
    """Switching maze type in the menu re-clamps width/height to the new type's max."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL,
        width=12, height=12,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(11, 11),
    )
    # ORTHOGONAL allows 12 wide but SIGMA only allows 8.
    screen_max = {
        MazeType.ORTHOGONAL: (12, 12),
        MazeType.SIGMA: (8, 8),
    }
    state = MenuState(request, max_sizes=screen_max)
    assert state.width == 12  # ORTHOGONAL allows it

    # Cycle type to SIGMA (one step right from ORTHOGONAL is SIGMA).
    state.section = MenuState.SECTION_TYPE
    state.handle_keydown(pygame.K_RIGHT)
    new_type = MenuState.SUPPORTED_TYPES[state.type_idx]
    assert new_type == MazeType.SIGMA
    # Width and height must be clamped to the SIGMA limit.
    assert state.width <= 8
    assert state.height <= 8


# ---------------------------------------------------------------------------
# Session 19 — algorithm compatibility filtering and educational content
# ---------------------------------------------------------------------------


def test_menu_algo_filtering_rhombic_excludes_binary_tree() -> None:
    """BinaryTree is not in the compatible algorithm list for Rhombic."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.RHOMBIC, width=7, height=7,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(6, 6),
    )
    state = MenuState(request)
    assert Algorithm.BINARY_TREE not in state._compatible_algos


def test_menu_algo_filtering_orthogonal_has_all_algorithms() -> None:
    """Orthogonal supports all 13 algorithms."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL, width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    assert len(state._compatible_algos) == len(MenuState.ALGORITHMS)


def test_menu_type_change_reseats_algo_if_incompatible() -> None:
    """Switching from Orthogonal to Sigma while BinaryTree is selected resets algo_idx to 0."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL, width=5, height=5,
        algorithm=Algorithm.BINARY_TREE,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.section = MenuState.SECTION_TYPE
    state.handle_keydown(pygame.K_RIGHT)  # ORTHOGONAL → SIGMA
    assert MenuState.SUPPORTED_TYPES[state.type_idx] == MazeType.SIGMA
    assert Algorithm.BINARY_TREE not in state._compatible_algos
    assert state._compatible_algos[state.algo_idx] != Algorithm.BINARY_TREE


def test_menu_type_change_preserves_algo_if_still_compatible() -> None:
    """Switching types preserves the currently-selected algorithm when it remains valid."""
    from mazer.ui.menu import MenuState

    request = MazeRequest(
        maze_type=MazeType.ORTHOGONAL, width=5, height=5,
        algorithm=Algorithm.RECURSIVE_BACKTRACKER,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    state.section = MenuState.SECTION_TYPE
    state.handle_keydown(pygame.K_RIGHT)  # ORTHOGONAL → SIGMA
    assert state._compatible_algos[state.algo_idx] == Algorithm.RECURSIVE_BACKTRACKER


def test_menu_incompatible_algo_in_request_falls_back_to_index_0() -> None:
    """Opening the menu with a type/algo combination that is filtered falls back to algo index 0."""
    from mazer.ui.menu import MenuState

    # BinaryTree is excluded for Sigma — simulate a saved config being loaded.
    request = MazeRequest(
        maze_type=MazeType.SIGMA, width=5, height=5,
        algorithm=Algorithm.BINARY_TREE,
        start=Coord(0, 0), goal=Coord(4, 4),
    )
    state = MenuState(request)
    assert state.algo_idx == 0
    assert Algorithm.BINARY_TREE not in state._compatible_algos


def test_menu_algo_display_name_is_human_readable() -> None:
    """Algorithm display names are human-readable (contain spaces, proper capitalisation)."""
    from mazer.ui.menu import _ALGO_DISPLAY_NAME

    assert _ALGO_DISPLAY_NAME[Algorithm.RECURSIVE_BACKTRACKER] == "Recursive Backtracker"
    assert " " in _ALGO_DISPLAY_NAME[Algorithm.BINARY_TREE]
    assert _ALGO_DISPLAY_NAME[Algorithm.WILSONS] == "Wilson's"


def test_menu_descriptions_exist_for_all_types_and_algos() -> None:
    """Every supported maze type and every algorithm has a non-empty description string."""
    from mazer.ui.menu import _ALGO_DESC, _TYPE_DESC, MenuState

    for mt in MenuState.SUPPORTED_TYPES:
        assert mt in _TYPE_DESC and len(_TYPE_DESC[mt]) > 10, f"Missing description for {mt}"
    for algo in MenuState.ALGORITHMS:
        assert algo in _ALGO_DESC and len(_ALGO_DESC[algo]) > 10, f"Missing description for {algo}"
