"""Pygame renderer for orthogonal mazes.

Look-and-feel mirrors the iOS reference app
(``.planning/referenced_resources/iOS_app/mazer-ios/Views/MazeComponents/
OrthogonalCellView.swift`` and ``Layout/MazeCellAppearance.swift``):

* Wall stroke = ``cell_size // 6`` — the orthogonal denominator from
  ``wallStrokeWidth(for: .orthogonal, ...)``.
* Heatmap default is the "Belize Hole" 10-shade gradient from
  ``HeatMapPalette.swift``; index = ``min(9, distance * 10 / max_distance)``.
* Cell background uses ``CellColors.offWhite`` (#FFF5E6) with the same
  subtle row-based gradient toward white at the top that the iOS code
  applies via ``cellBackgroundColor(... totalRows: ...)``.
* Start / goal / visited / solution colors are taken directly from
  ``CellColors``.

The renderer is orthogonal-only by design (Stage 4 scope). The ``Cell``
objects it consumes already carry ``maze_type`` so a future polymorphic
renderer can dispatch on it without changing this module's surface.
"""

from __future__ import annotations

import pygame

from mazer.maze import Cell
from mazer.types import Direction


# --- iOS palette (CellColors / SwiftUI defaults) --------------------------

OFF_WHITE = (255, 245, 230)            # CellColors.offWhite (#FFF5E6)
START_COLOR = (0, 122, 255)            # SwiftUI .blue
GOAL_COLOR = (255, 59, 48)             # SwiftUI .red
VISITED_COLOR = (255, 120, 180)        # CellColors.traversedPathColor
SOLUTION_COLOR = (116, 180, 191)       # midpoint of vividBlue and gray (CellColors.solutionPathColor)
ACTIVE_MARKER_COLOR = (250, 200, 0)    # warm yellow — distinct from start/goal/solution
WALL_COLOR = (0, 0, 0)
BORDER_COLOR = (0, 0, 0)
LETTER_COLOR = (255, 255, 255)


# Belize Hole palette from HeatMapPalette.swift (light → dark).
HEATMAP_BELIZE_HOLE = (
    (234, 242, 248),
    (212, 230, 241),
    (169, 204, 227),
    (127, 179, 213),
    (84, 153, 199),
    (41, 128, 185),
    (36, 113, 163),
    (31, 97, 141),
    (26, 82, 118),
    (21, 67, 96),
)

BORDER_WIDTH = 4


def _interp(c1: tuple[int, int, int], c2: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (
        int(round(c1[0] + factor * (c2[0] - c1[0]))),
        int(round(c1[1] + factor * (c2[1] - c1[1]))),
        int(round(c1[2] + factor * (c2[2] - c1[2]))),
    )


def _heatmap_color(distance: int, max_distance: int, palette) -> tuple[int, int, int]:
    if max_distance <= 0:
        return palette[0]
    idx = min(9, (distance * 10) // max_distance)
    return palette[idx]


def _default_cell_color(y: int, total_rows: int) -> tuple[int, int, int]:
    """Subtle top-to-bottom gradient (near-white → off-white)."""
    if total_rows <= 1:
        return OFF_WHITE
    start = _interp(OFF_WHITE, (255, 255, 255), 0.9)
    return _interp(start, OFF_WHITE, y / (total_rows - 1))


class Renderer:
    """Renders an orthogonal maze onto a Pygame surface.

    ``offset`` shifts the maze inside the surface so the caller can reserve
    pixels at the top for a HUD without the renderer needing to know about it.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        cell_size: int,
        offset: tuple[int, int] = (0, 0),
        palette=HEATMAP_BELIZE_HOLE,
    ) -> None:
        self.surface = surface
        self.cell_size = cell_size
        self.offset_x, self.offset_y = offset
        self.palette = palette
        self.wall_width = max(1, cell_size // 6)
        self._marker_font = pygame.font.SysFont(None, max(14, int(cell_size * 0.9)))

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool) -> None:
        if not cells:
            return
        max_distance = max(c.distance for c in cells)
        total_cols = max(c.coord.x for c in cells) + 1
        total_rows = max(c.coord.y for c in cells) + 1
        maze_rect = pygame.Rect(
            self.offset_x,
            self.offset_y,
            total_cols * self.cell_size,
            total_rows * self.cell_size,
        )

        pygame.draw.rect(self.surface, OFF_WHITE, maze_rect)
        for cell in cells:
            self._draw_cell(cell, max_distance, total_rows, show_heatmap, show_solution)
        pygame.draw.rect(self.surface, BORDER_COLOR, maze_rect, BORDER_WIDTH)

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        """Bounding rect of the painted maze (for overlays drawn by the app)."""
        cols = max((c.coord.x for c in cells), default=0) + 1
        rows = max((c.coord.y for c in cells), default=0) + 1
        return pygame.Rect(
            self.offset_x, self.offset_y, cols * self.cell_size, rows * self.cell_size
        )

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(
            self.offset_x + x * self.cell_size,
            self.offset_y + y * self.cell_size,
            self.cell_size,
            self.cell_size,
        )

    def _cell_color(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
    ) -> tuple[int, int, int]:
        if cell.is_start:
            return START_COLOR
        if cell.is_goal:
            return GOAL_COLOR
        if cell.is_visited:
            return VISITED_COLOR
        if show_solution and cell.on_solution_path:
            return SOLUTION_COLOR
        if show_heatmap and max_distance > 0:
            return _heatmap_color(cell.distance, max_distance, self.palette)
        return _default_cell_color(cell.coord.y, total_rows)

    def _draw_cell(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
    ) -> None:
        rect = self._cell_rect(cell.coord.x, cell.coord.y)
        pygame.draw.rect(
            self.surface,
            self._cell_color(cell, max_distance, total_rows, show_heatmap, show_solution),
            rect,
        )

        w = self.wall_width
        if Direction.UP not in cell.linked:
            pygame.draw.rect(self.surface, WALL_COLOR, pygame.Rect(rect.left, rect.top, rect.width, w))
        if Direction.DOWN not in cell.linked:
            pygame.draw.rect(
                self.surface, WALL_COLOR,
                pygame.Rect(rect.left, rect.bottom - w, rect.width, w),
            )
        if Direction.LEFT not in cell.linked:
            pygame.draw.rect(self.surface, WALL_COLOR, pygame.Rect(rect.left, rect.top, w, rect.height))
        if Direction.RIGHT not in cell.linked:
            pygame.draw.rect(
                self.surface, WALL_COLOR,
                pygame.Rect(rect.right - w, rect.top, w, rect.height),
            )

        if cell.is_start:
            self._draw_letter(rect, "A")
        elif cell.is_goal:
            self._draw_letter(rect, "B")

        if cell.is_active:
            radius = max(3, self.cell_size // 4)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, rect.center, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, rect.center, radius, max(1, w // 2))

    def _draw_letter(self, rect: pygame.Rect, letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=rect.center))


__all__ = ["Renderer", "OFF_WHITE", "HEATMAP_BELIZE_HOLE"]
