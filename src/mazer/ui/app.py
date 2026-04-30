"""Pygame entry point: window, default maze, and game loop.

Defaults are picked per maze type. Orthogonal: 20×20 grid, ~28px cells —
the same band the iOS reference app's "medium" preset uses. Sigma: 11×10
grid at 26px so the hex bounding box lands in a similar window footprint
without becoming uncomfortably tall (sqrt(3) ≈ 1.73 makes hex windows
naturally taller than square ones).

CLI:
    python -m mazer                     # default Orthogonal
    python -m mazer --type sigma        # hexagonal grid
    python -m mazer --type sigma --width 13 --height 11 --algo HuntAndKill

Movement input (works for every maze type):
    Single arrow keys → cardinal direction (UP/DOWN/LEFT/RIGHT).
    Held arrow chords → diagonal direction:
        ↑ + →  → UPPER_RIGHT
        ↑ + ←  → UPPER_LEFT
        ↓ + →  → LOWER_RIGHT
        ↓ + ←  → LOWER_LEFT
    Left mouse button on an *adjacent linked* cell → move there (single
    tap). Click-and-drag across the grid → chains moves cell-by-cell as
    the cursor crosses open walls (continuous trackpad/mouse navigation).

    The Rust ``make_move`` has built-in fallback for every direction
    (e.g. UPPER_RIGHT tries UpperRight → Up → Right), so chords work
    naturally on orthogonal too — pressing ↑+→ moves up if available,
    else right. Same forgiving feel as the iOS app's eight-way controls.

Sigma also keeps the legacy "hex roguelike" key layout for muscle memory:
    W                UP             Q                UPPER_LEFT
    X                DOWN           E                UPPER_RIGHT
                                    Z                LOWER_LEFT
                                    C                LOWER_RIGHT

Common keys:
    H                Toggle heatmap overlay
    S                Toggle solution-path overlay
    R                Regenerate with the current request (same params)
    N                "New maze" — alias for R; reserved for a real picker
                     dialog later. Behaves identically.
    Esc              Quit (window close also quits).

Open-exit dots: the active cell shows small white dots near each open
edge — affordance equivalent to the iOS D-pad's per-direction enabled
state. If a key seems "not to move you", check the dots.
"""

from __future__ import annotations

import argparse

import pygame

from mazer.maze import Cell, Maze
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType
from mazer.ui.renderer import (
    OFF_WHITE,
    make_renderer,
    orthogonal_direction,
    sigma_direction,
)


HUD_HEIGHT = 56

# Per-maze-type defaults. Tuple of (cell_size, width, height) — the
# default algorithm is the same (RecursiveBacktracker) for both because
# it produces winding paths that show off the heatmap and solution-path
# overlays well; user can override with --algo.
_DEFAULTS: dict[MazeType, tuple[int, int, int]] = {
    MazeType.ORTHOGONAL: (28, 20, 20),
    MazeType.SIGMA: (26, 11, 10),
}

ORTHOGONAL_KEYS: dict[int, Direction] = {
    pygame.K_UP: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
}

# Sigma uses the standard hex roguelike layout: W/Q/E across the top row
# of letters and Z/X/C across the bottom row, with the grid pivot point
# (S/D in QWERTY) deliberately *unbound* so a typo in either row never
# silently wraps. ↑ and ↓ also map to UP/DOWN as a common-sense affordance.
SIGMA_KEYS: dict[int, Direction] = {
    pygame.K_UP: Direction.UP,
    pygame.K_w: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_x: Direction.DOWN,
    pygame.K_q: Direction.UPPER_LEFT,
    pygame.K_e: Direction.UPPER_RIGHT,
    pygame.K_z: Direction.LOWER_LEFT,
    pygame.K_c: Direction.LOWER_RIGHT,
}

_KEYS_BY_TYPE: dict[MazeType, dict[int, Direction]] = {
    MazeType.ORTHOGONAL: ORTHOGONAL_KEYS,
    MazeType.SIGMA: SIGMA_KEYS,
}

ARROW_KEYS: tuple[int, ...] = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT)

_HUD_HINT_BY_TYPE: dict[MazeType, str] = {
    MazeType.ORTHOGONAL: "arrows + chords + drag/click to move",
    MazeType.SIGMA: "arrow chords / W·Q·E·Z·X·C / drag/click to move",
}


def _resolve_chord(up: bool, down: bool, left: bool, right: bool) -> Direction | None:
    """Resolve held arrow keys to a single Direction.

    Diagonal combinations win over cardinals. Opposing pairs (UP+DOWN,
    LEFT+RIGHT) cancel out — they're treated as if the perpendicular axis
    isn't held, so e.g. UP+DOWN+RIGHT resolves to RIGHT.

    Returns ``None`` if no arrow is held (callers shouldn't reach this
    case on KEYDOWN — defensive only).
    """
    vertical = up ^ down  # cancel if both
    horizontal = left ^ right
    if vertical and horizontal:
        if up and right:
            return Direction.UPPER_RIGHT
        if up and left:
            return Direction.UPPER_LEFT
        if down and right:
            return Direction.LOWER_RIGHT
        if down and left:
            return Direction.LOWER_LEFT
    if vertical:
        return Direction.UP if up else Direction.DOWN
    if horizontal:
        return Direction.LEFT if left else Direction.RIGHT
    return None


def _direction_for_click(
    active: Cell, target_coord: Coord, cells: list[Cell], maze_type: MazeType
) -> Direction | None:
    """Look up the direction that connects active → clicked, if linked.

    Orthogonal: trivial 4-adjacent delta lookup.
    Sigma: read the direction name from ``active.linked`` so we send the
    *exact* name the FFI used, sidestepping the boundary-clamp ambiguity.
    Returns ``None`` if the click was on a non-adjacent or non-linked cell.
    """
    if target_coord == active.coord:
        return None
    if maze_type == MazeType.ORTHOGONAL:
        direction = orthogonal_direction(active.coord, target_coord)
        if direction is None or direction not in active.linked:
            return None
        return direction
    if maze_type == MazeType.SIGMA:
        return sigma_direction(active, target_coord, cells)
    return None

class _DragState:
    """Mouse drag state machine for continuous multi-cell navigation.

    BUTTONDOWN → ``begin`` (fires the first move if on an adjacent linked cell
    and starts the drag session). MOUSEMOTION → ``motion`` (fires a move each
    time the cursor enters a new adjacent linked cell). BUTTONUP → ``end``.

    Single tap is the degenerate case: BUTTONDOWN fires the move, no MOTION
    event crosses a new cell boundary before BUTTONUP ends the session.
    """

    def __init__(self) -> None:
        self.active = False

    def begin(
        self,
        pos: tuple[int, int],
        renderer,
        maze,
        cells: list,
        maze_type: MazeType,
    ) -> bool:
        """Start a drag session. Returns True if a move was fired."""
        self.active = True
        target = renderer.cell_at(pos, cells)
        if target is None:
            return False
        active_cell = next((c for c in cells if c.is_active), None)
        if active_cell is None:
            return False
        direction = _direction_for_click(active_cell, target, cells, maze_type)
        if direction is not None:
            return maze.move(direction)
        return False

    def motion(
        self,
        pos: tuple[int, int],
        renderer,
        maze,
        maze_type: MazeType,
    ) -> bool:
        """Handle MOUSEMOTION. Fires a move if the cursor entered a new adjacent linked cell."""
        if not self.active:
            return False
        cells = maze.cells()
        active_cell = next((c for c in cells if c.is_active), None)
        if active_cell is None:
            return False
        target = renderer.cell_at(pos, cells)
        if target is None or target == active_cell.coord:
            return False
        direction = _direction_for_click(active_cell, target, cells, maze_type)
        if direction is not None:
            return maze.move(direction)
        return False

    def end(self) -> None:
        self.active = False


HUD_BG = OFF_WHITE
HUD_TITLE_COLOR = (40, 40, 40)
HUD_HINT_COLOR = (90, 90, 90)
SOLVED_TEXT_COLOR = (255, 255, 255)
SOLVED_OVERLAY_RGBA = (0, 0, 0, 130)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m mazer", description="Mazer Pygame UI.")
    parser.add_argument(
        "--type",
        dest="maze_type",
        choices=[m.value.lower() for m in (MazeType.ORTHOGONAL, MazeType.SIGMA)],
        default=MazeType.ORTHOGONAL.value.lower(),
        help="Maze type. Stage 6 supports orthogonal (default) and sigma (hex).",
    )
    parser.add_argument("--width", type=int, default=None, help="Grid width (cells). Default depends on type.")
    parser.add_argument("--height", type=int, default=None, help="Grid height (cells). Default depends on type.")
    parser.add_argument(
        "--algo",
        default=Algorithm.RECURSIVE_BACKTRACKER.value,
        help=f"Generation algorithm. Default {Algorithm.RECURSIVE_BACKTRACKER.value}.",
    )
    return parser.parse_args(argv)


def _build_request(args: argparse.Namespace) -> tuple[MazeRequest, int]:
    """Translate CLI args into a (request, cell_size) pair."""
    maze_type = MazeType(args.maze_type.capitalize())
    cell_size, default_w, default_h = _DEFAULTS[maze_type]
    width = args.width if args.width is not None else default_w
    height = args.height if args.height is not None else default_h
    algorithm = Algorithm(args.algo)
    request = MazeRequest(
        maze_type=maze_type,
        width=width,
        height=height,
        algorithm=algorithm,
        capture_steps=False,
        start=Coord(x=0, y=0),
        goal=Coord(x=width - 1, y=height - 1),
    )
    return request, cell_size


def _window_size(request: MazeRequest, cell_size: int) -> tuple[int, int]:
    """Compute the window size for a request without touching pygame.

    Orthogonal: width = W*cell, height = H*cell + HUD.
    Sigma: bounding box from the iOS reference's hex layout, plus HUD.
    """
    if request.maze_type == MazeType.ORTHOGONAL:
        return (request.width * cell_size, request.height * cell_size + HUD_HEIGHT)
    if request.maze_type == MazeType.SIGMA:
        # Pull the same math the renderer uses; importing inline avoids a
        # top-level dependency on math just for window sizing.
        import math

        hex_height = math.sqrt(3) * cell_size
        w = int(round(cell_size * (1.5 * request.width + 0.5)))
        h = int(round(hex_height * (request.height + 0.5))) + HUD_HEIGHT
        return (w, h)
    raise NotImplementedError(f"window sizing for {request.maze_type.value}")


def _is_solved(cells) -> bool:
    return any(c.is_active and c.is_goal for c in cells)


def _draw_hud(
    surface: pygame.Surface,
    font: pygame.font.Font,
    request: MazeRequest,
    show_heatmap: bool,
    show_solution: bool,
    solved: bool,
) -> None:
    pygame.draw.rect(surface, HUD_BG, pygame.Rect(0, 0, surface.get_width(), HUD_HEIGHT))
    title = f"{request.maze_type.value} · {request.algorithm.value}  {request.width}×{request.height}"
    move_hint = _HUD_HINT_BY_TYPE.get(request.maze_type, "")
    hints = (
        f"H heatmap:{'on' if show_heatmap else 'off'}    "
        f"S solution:{'on' if show_solution else 'off'}    "
        f"R regen    N new    {move_hint}"
    )
    surface.blit(font.render(title, True, HUD_TITLE_COLOR), (12, 8))
    surface.blit(font.render(hints, True, HUD_HINT_COLOR), (12, 30))
    if solved:
        msg = font.render("Solved!", True, (16, 130, 60))
        surface.blit(msg, msg.get_rect(midright=(surface.get_width() - 12, HUD_HEIGHT // 2)))


def _draw_solved_overlay(
    surface: pygame.Surface,
    rect: pygame.Rect,
    big_font: pygame.font.Font,
    hint_font: pygame.font.Font,
) -> None:
    overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
    overlay.fill(SOLVED_OVERLAY_RGBA)
    surface.blit(overlay, rect.topleft)
    text = big_font.render("Solved!", True, SOLVED_TEXT_COLOR)
    text_rect = text.get_rect(center=rect.center)
    surface.blit(text, text_rect)
    hint = hint_font.render("Press R for a new maze", True, SOLVED_TEXT_COLOR)
    surface.blit(hint, hint.get_rect(midtop=(rect.centerx, text_rect.bottom + 8)))


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    request, cell_size = _build_request(args)
    key_map = _KEYS_BY_TYPE[request.maze_type]

    pygame.init()
    pygame.display.set_caption(
        f"Mazer — {request.maze_type.value} · {request.algorithm.value} {request.width}×{request.height}"
    )

    screen = pygame.display.set_mode(_window_size(request, cell_size))
    clock = pygame.time.Clock()
    hud_font = pygame.font.SysFont(None, 22)
    big_font = pygame.font.SysFont(None, 72)

    maze = Maze(request)
    renderer = make_renderer(request.maze_type, screen, cell_size, offset=(0, HUD_HEIGHT))
    show_heatmap = False
    show_solution = False
    # Once a chord fires from a multi-arrow KEYDOWN, mark every held arrow
    # as consumed so the *other* arrow's eventual KEYDOWN doesn't fire a
    # second move (or, if the user has key-repeat enabled externally, so
    # autorepeat doesn't spam the chord). Cleared on the matching KEYUP.
    arrows_consumed: set[int] = set()
    drag = _DragState()

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_h:
                        show_heatmap = not show_heatmap
                    elif event.key == pygame.K_s:
                        show_solution = not show_solution
                    elif event.key in (pygame.K_r, pygame.K_n):
                        maze.close()
                        maze = Maze(request)
                        arrows_consumed.clear()
                        drag.end()
                    elif event.key in ARROW_KEYS:
                        if event.key in arrows_consumed:
                            continue
                        keys = pygame.key.get_pressed()
                        direction = _resolve_chord(
                            keys[pygame.K_UP],
                            keys[pygame.K_DOWN],
                            keys[pygame.K_LEFT],
                            keys[pygame.K_RIGHT],
                        )
                        if direction is not None:
                            maze.move(direction)
                            held_arrows = [k for k in ARROW_KEYS if keys[k]]
                            if len(held_arrows) > 1:
                                arrows_consumed.update(held_arrows)
                    elif event.key in key_map:
                        maze.move(key_map[event.key])
                elif event.type == pygame.KEYUP and event.key in ARROW_KEYS:
                    arrows_consumed.discard(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    drag.begin(event.pos, renderer, maze, maze.cells(), request.maze_type)
                elif event.type == pygame.MOUSEMOTION:
                    drag.motion(event.pos, renderer, maze, request.maze_type)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    drag.end()

            cells = maze.cells()
            solved = _is_solved(cells)

            screen.fill((20, 20, 24))
            renderer.draw(cells, show_heatmap=show_heatmap, show_solution=show_solution)
            if solved:
                _draw_solved_overlay(screen, renderer.maze_rect(cells), big_font, hud_font)
            _draw_hud(screen, hud_font, request, show_heatmap, show_solution, solved)

            pygame.display.flip()
            clock.tick(60)
    finally:
        maze.close()
        pygame.quit()


if __name__ == "__main__":
    main()
