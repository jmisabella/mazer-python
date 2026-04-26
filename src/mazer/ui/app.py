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

Key bindings:
    Orthogonal:
        Arrow keys       Move (UP / DOWN / LEFT / RIGHT)
    Sigma (six directions, "hex roguelike" layout):
        ↑ or W           UP
        ↓ or X           DOWN
        Q                UPPER_LEFT
        E                UPPER_RIGHT
        Z                LOWER_LEFT
        C                LOWER_RIGHT
    Common:
        H                Toggle heatmap overlay
        S                Toggle solution-path overlay
        R                Regenerate with the current request (same params)
        N                "New maze" — Stage-4 alias for R; reserved for a
                         real picker dialog later. Behaves identically.
        Esc              Quit (window close also quits).

Why no Q-to-quit anymore: ``Q`` is now UPPER_LEFT in the sigma key map,
and keeping it as a quit shortcut only on Orthogonal would mean the same
key has different consequences in different modes. Esc + window-close is
unambiguous either way.
"""

from __future__ import annotations

import argparse

import pygame

from mazer.maze import Maze
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType
from mazer.ui.renderer import OFF_WHITE, make_renderer


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

_HUD_HINT_BY_TYPE: dict[MazeType, str] = {
    MazeType.ORTHOGONAL: "arrows: move",
    MazeType.SIGMA: "W/X/Q/E/Z/C: move",
}

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
                    elif event.key in key_map:
                        maze.move(key_map[event.key])

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
