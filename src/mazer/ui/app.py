"""Pygame entry point: window, default maze, and game loop.

Defaults are a 20×20 Orthogonal grid generated with Recursive Backtracker
and ~28px cells — the same size band the iOS reference app uses for its
"medium" orthogonal preset. ``start`` and ``goal`` are pinned to opposite
corners so the maze is solvable end-to-end on first launch.

Key bindings:
    Arrow keys   Move (Direction.UP / DOWN / LEFT / RIGHT)
    H            Toggle heatmap overlay
    S            Toggle solution-path overlay
    R            Regenerate with the current request (same params)
    N            "New maze" — Stage-4 alias for R; reserved for a real
                 dialog/picker in a later stage. Behaves identically for now.
    Esc / Q      Quit
"""

from __future__ import annotations

import pygame

from mazer.maze import Maze
from mazer.types import Algorithm, Coord, Direction, MazeRequest, MazeType
from mazer.ui.renderer import OFF_WHITE, Renderer


CELL_SIZE = 28
HUD_HEIGHT = 56

DEFAULT_REQUEST = MazeRequest(
    maze_type=MazeType.ORTHOGONAL,
    width=20,
    height=20,
    algorithm=Algorithm.RECURSIVE_BACKTRACKER,
    capture_steps=False,
    start=Coord(x=0, y=0),
    goal=Coord(x=19, y=19),
)

KEY_TO_DIRECTION = {
    pygame.K_UP: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
}

HUD_BG = OFF_WHITE
HUD_TITLE_COLOR = (40, 40, 40)
HUD_HINT_COLOR = (90, 90, 90)
SOLVED_TEXT_COLOR = (255, 255, 255)
SOLVED_OVERLAY_RGBA = (0, 0, 0, 130)


def _window_size(request: MazeRequest, cell_size: int) -> tuple[int, int]:
    return (request.width * cell_size, request.height * cell_size + HUD_HEIGHT)


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
    title = f"{request.algorithm.value}  {request.width}×{request.height}"
    hints = (
        f"H heatmap:{'on' if show_heatmap else 'off'}    "
        f"S solution:{'on' if show_solution else 'off'}    "
        "R regen    N new    arrows: move"
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


def main() -> None:
    pygame.init()
    pygame.display.set_caption(
        f"Mazer — {DEFAULT_REQUEST.algorithm.value} {DEFAULT_REQUEST.width}×{DEFAULT_REQUEST.height}"
    )

    screen = pygame.display.set_mode(_window_size(DEFAULT_REQUEST, CELL_SIZE))
    clock = pygame.time.Clock()
    hud_font = pygame.font.SysFont(None, 22)
    big_font = pygame.font.SysFont(None, 72)

    request = DEFAULT_REQUEST
    maze = Maze(request)
    renderer = Renderer(screen, CELL_SIZE, offset=(0, HUD_HEIGHT))
    show_heatmap = False
    show_solution = False

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_h:
                        show_heatmap = not show_heatmap
                    elif event.key == pygame.K_s:
                        show_solution = not show_solution
                    elif event.key in (pygame.K_r, pygame.K_n):
                        maze.close()
                        maze = Maze(request)
                    elif event.key in KEY_TO_DIRECTION:
                        maze.move(KEY_TO_DIRECTION[event.key])

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
