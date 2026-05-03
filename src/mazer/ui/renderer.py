"""Pygame renderers for each maze type.

Look-and-feel mirrors the iOS reference app
(``.planning/referenced_resources/iOS_app/mazer-ios/Views/MazeComponents/``
and ``Layout/MazeCellAppearance.swift``):

* Wall stroke for orthogonal = ``cell_size // 12``; for sigma it's
  ``cell_size // 6`` at ``cell_size >= 18`` and ``cell_size // 7`` below;
  for delta ``cell_size / 10 * 1.15`` at ``cell_size >= 28`` else
  ``cell_size / 12 * 1.15``; for rhombic ``cell_size / 7`` at
  ``cell_size >= 18`` else ``cell_size / 4.8``; for upsilon
  ``cell_size / 12`` at ``cell_size >= 28`` else ``cell_size / 16``
  (denominators from ``wallStrokeWidth(for:cellSize:)``).
* Heatmap default is the "Belize Hole" 10-shade gradient from
  ``HeatMapPalette.swift``; index = ``min(9, distance * 10 / max_distance)``.
* Cell background uses ``CellColors.offWhite`` (#FFF5E6) with the same
  subtle row-based gradient toward white at the top that the iOS code
  applies via ``cellBackgroundColor(... totalRows: ...)``.
* Start / goal / visited / solution colors are taken directly from
  ``CellColors``.

Dispatch:
    All renderer classes expose ``draw(cells, show_heatmap, show_solution)``
    and ``maze_rect(cells)``. The app picks the right one for a maze via
    :func:`make_renderer`. All five maze types are implemented.

Hex layout (Sigma):
    Flat-top hexagons in odd-q vertical offset, ported from the iOS
    ``SigmaCellView``/``SigmaMazeView`` pair. Unit-hexagon vertices in
    ``cell_size`` units::

        (0.5, 0)      (1.5, 0)
        (0,   h/2)               (2, h/2)     where h = sqrt(3)
        (0.5, h)      (1.5, h)

    Direction → edge (vertex-index pair) ported from
    ``HexDirection.vertexIndices``: UP=(0,1), UPPER_RIGHT=(1,2),
    LOWER_RIGHT=(2,3), DOWN=(3,4), LOWER_LEFT=(4,5), UPPER_LEFT=(5,0).

Triangle layout (Delta):
    Equilateral triangles alternating upward (Normal) and downward (Inverted)
    in each row, ported from ``DeltaCellView``/``DeltaMazeView``. Each
    triangle has bounding-box width ``cell_size`` and height
    ``cell_size * sqrt(3) / 2``. Adjacent cells share a ``cell_size / 2``
    overlap (HStack spacing = ``-cell_size / 2`` in iOS). Cell (col, row)
    has its bounding-rect left edge at ``col * cell_size / 2``.

    Orientation: ``(col + row) % 2 == 0`` → Normal (apex up), else Inverted
    (apex down). Directions:
      Normal  — UpperLeft (left slant), UpperRight (right slant), Down (base).
      Inverted — Up (top base), LowerLeft (left slant), LowerRight (right slant).

Diamond layout (Rhombic):
    45°-rotated diamond cells, ported from ``RhombicCellView``/
    ``RhombicMazeView``. Only cells where ``(col + row) % 2 == 0`` exist
    (checkerboard pattern). Bounding box per diamond is ``box × box`` where
    ``box = cell_size * sqrt(2)``; cell center in the grid is at
    ``(col * half_diagonal, row * half_diagonal)`` where
    ``half_diagonal = box / 2``.

    Unit points (scaled by ``box``): top=(0.5,0), right=(1,0.5),
    bottom=(0.5,1), left=(0,0.5). Directions:
      UpperRight — top → right (vertices 0→1).
      LowerRight — right → bottom (vertices 1→2).
      LowerLeft  — bottom → left (vertices 2→3).
      UpperLeft  — left → top (vertices 3→0).

    Container: ``half_diagonal * max_x + box`` wide,
    ``half_diagonal * max_y + box`` tall.

Upsilon layout (octagon + square mix):
    Alternating octagon and square cells. ``is_square`` is True when
    ``(col + row) % 2 == 1`` (checkerboard pattern). ``squareSize``
    = ``cell_size * (sqrt(2) - 1)`` (from iOS ``MazeLayoutMetrics.swift``).
    Both cell types share the same center-to-center step:
    ``step = cell_size * sqrt(2) / 2``. Cell (col, row) center:
    ``cx = col * step + cell_size/2``, ``cy = row * step + cell_size/2``.

    Octagon vertices (r = cell_size/2, k = 2r/(2+sqrt(2))), centered at (cx, cy)::

        0: (cx-r+k, cy-r)   1: (cx+r-k, cy-r)
        7: (cx-r, cy-r+k)                       2: (cx+r, cy-r+k)
        6: (cx-r, cy+r-k)                       3: (cx+r, cy+r-k)
        5: (cx-r+k, cy+r)   4: (cx+r-k, cy+r)

    Direction → edge for octagon (ported from ``UpsilonCellView.swift``):
      Up=(0,1), UpperRight=(1,2), Right=(2,3), LowerRight=(3,4),
      Down=(4,5), LowerLeft=(5,6), Left=(6,7), UpperLeft=(7,0).

    Square vertices (side = squareSize, centered at (cx, cy)):
      0: top-left, 1: top-right, 2: bottom-right, 3: bottom-left.
    Direction → edge for square: Up=(0,1), Right=(1,2), Down=(2,3), Left=(3,0).

    Container: ``(cols-1) * step + cell_size`` wide,
    ``(rows-1) * step + cell_size`` tall.
"""

from __future__ import annotations

import math
import random
from typing import NamedTuple

import pygame

from mazer.maze import Cell
from mazer.types import Coord, Direction, MazeType


# --- iOS palette (CellColors / SwiftUI defaults) --------------------------

OFF_WHITE = (255, 245, 230)            # CellColors.offWhite (#FFF5E6)
START_COLOR = (0, 122, 255)            # SwiftUI .blue
GOAL_COLOR = (255, 59, 48)             # SwiftUI .red
VISITED_COLOR = (255, 120, 180)        # CellColors.traversedPathColor
ACTIVE_CELL_COLOR = (180, 15, 95)      # darkest fuchsia — current player cell background
TRAIL_COLORS = [                       # index 0 = 1 step back (darkest), index 2 = 3 steps back (lightest)
    (210, 40, 120),
    (235, 75, 148),
    (248, 105, 167),
]
SOLUTION_COLOR = (116, 180, 191)       # midpoint of vividBlue and gray (CellColors.solutionPathColor)
ACTIVE_MARKER_COLOR = (250, 200, 0)    # warm yellow — distinct from start/goal/solution
OPEN_EXIT_DOT_COLOR = (255, 255, 255)  # contrast against any cell background
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

# sqrt(3) shows up everywhere in flat-top hex math — name it once.
_SQRT3 = math.sqrt(3)


# --- Gradient theme -------------------------------------------------------

class GradientTheme(NamedTuple):
    """Two-color per-row gradient for default cell backgrounds.

    Mirrors the iOS ``cellBackgroundColor`` logic: a subtle row-based lerp
    from a slightly-tinted ``base`` at the top row back to ``base`` at the
    bottom.  When ``accent`` is set the top-row tint is
    ``lerp(base, accent, 0.17)``; when it's ``None`` the tint is
    ``lerp(base, white, 0.9)`` (the existing plain near-white look).
    """
    base: tuple[int, int, int]
    accent: tuple[int, int, int] | None


# Ported from CellColors.defaultBackgroundColors in the iOS reference.
_DEFAULT_BG_COLORS: tuple[tuple[int, int, int], ...] = (
    (200, 235, 215),   # mint
    (255, 215, 200),   # peach
    (255, 245, 230),   # offWhite
    (214, 236, 243),   # lighterSky
    (250, 249, 251),   # barelyLavenderMostlyWhite
    (169, 220, 237),   # lighterSkyDarker
    (224, 215, 234),   # barelyLavenderMostlyWhiteDarker
    (156, 228, 187),   # mintDarker
    (255, 178, 149),   # peachDarker
    (250, 218, 221),   # softPastelPinkLight
    (255, 250, 205),   # softPastelYellowLight
    (255, 218, 185),   # softPastelYellowishPink
    (215, 189, 226),   # softPastelPurplishBlueLavender
)

# SwiftUI named colors used as optional accent tint (ported from ContentView.swift).
_ACCENT_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 192, 203),   # .pink
    (128, 128, 128),   # .gray
    (255, 213, 0),     # .yellow
    (0, 122, 255),     # .blue
    (128, 0, 128),     # .purple
    (255, 149, 0),     # .orange
)


def generate_gradient(
    prev_base: tuple[int, int, int] | None = None,
) -> GradientTheme:
    """Return a randomly-chosen gradient theme for a new maze.

    Matches the iOS app: a fresh base color (excluding the previous one
    to avoid visual repetition) and a 50% chance of an accent tint.
    """
    choices = [c for c in _DEFAULT_BG_COLORS if c != prev_base]
    if not choices:
        choices = list(_DEFAULT_BG_COLORS)
    base = random.choice(choices)
    accent = random.choice(_ACCENT_COLORS) if random.random() < 0.5 else None
    return GradientTheme(base=base, accent=accent)


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


def _default_cell_color(
    y: int,
    total_rows: int,
    gradient: GradientTheme | None = None,
) -> tuple[int, int, int]:
    """Row-based gradient for plain (non-heatmap) cell backgrounds.

    With a ``GradientTheme``: mirrors iOS ``cellBackgroundColor`` — lerp the
    base toward the accent (factor 0.17) to form the top-row color, then
    lerp back to base at the bottom row.  Without one: falls back to the
    original near-white → off-white sweep.
    """
    base = gradient.base if gradient is not None else OFF_WHITE
    if total_rows <= 1:
        return base
    if gradient is not None and gradient.accent is not None:
        top = _interp(base, gradient.accent, 0.17)
    else:
        top = _interp(base, (255, 255, 255), 0.9)
    return _interp(top, base, y / (total_rows - 1))


def cell_color(
    cell: Cell,
    max_distance: int,
    total_rows: int,
    show_heatmap: bool,
    show_solution: bool,
    palette,
    gradient: GradientTheme | None = None,
    trail: dict | None = None,
    solution_revealed: frozenset | None = None,
) -> tuple[int, int, int]:
    """Decision chain for a cell's fill color.

    Mirrors ``cellBackgroundColor(...)`` in the iOS code: start > goal >
    visited > (solution overlay) > (heatmap) > default-row-gradient.
    Shared between every renderer so toggle behavior stays identical.

    ``solution_revealed``: when None, all solution-path cells are shown;
    when a frozenset, only cells whose coord is in the set are shown
    (used during the animated reveal).
    """
    if cell.is_start:
        return START_COLOR
    if cell.is_goal:
        return GOAL_COLOR
    if cell.is_active:
        return ACTIVE_CELL_COLOR
    if trail and cell.coord in trail:
        return TRAIL_COLORS[trail[cell.coord]]
    if cell.is_visited:
        return VISITED_COLOR
    if show_solution and cell.on_solution_path:
        if solution_revealed is None or cell.coord in solution_revealed:
            return SOLUTION_COLOR
    if show_heatmap and max_distance > 0:
        return _heatmap_color(cell.distance, max_distance, palette)
    return _default_cell_color(cell.coord.y, total_rows, gradient)


# --- Orthogonal helpers ---------------------------------------------------

# Cardinal direction → (dx, dy) in grid coords. Used by both the orthogonal
# renderer's open-exit dots and the click-to-move direction lookup.
ORTHO_OFFSETS: dict[Direction, tuple[int, int]] = {
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}


def orthogonal_direction(active: Coord, target: Coord) -> Direction | None:
    """Resolve the cardinal direction from ``active`` to an adjacent ``target``.

    Returns ``None`` if the two coords aren't 4-adjacent.
    """
    delta = (target.x - active.x, target.y - active.y)
    for direction, off in ORTHO_OFFSETS.items():
        if off == delta:
            return direction
    return None


# --- Orthogonal -----------------------------------------------------------


class OrthogonalRenderer:
    """Renders an orthogonal (square-cell) maze onto a Pygame surface.

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
        self.wall_width = max(1, cell_size // 12)
        self._marker_font = pygame.font.SysFont(None, max(14, int(cell_size * 0.9)))
        self.gradient: GradientTheme | None = None

    def set_gradient(self, gradient: GradientTheme | None) -> None:
        self.gradient = gradient

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool, trail: list | None = None, solution_revealed: frozenset | None = None) -> None:
        if not cells:
            return
        self._trail_dict: dict = {coord: i for i, coord in enumerate(trail)} if trail else {}
        max_distance = max(c.distance for c in cells)
        total_cols = max(c.coord.x for c in cells) + 1
        total_rows = max(c.coord.y for c in cells) + 1
        rect = pygame.Rect(
            self.offset_x,
            self.offset_y,
            total_cols * self.cell_size,
            total_rows * self.cell_size,
        )

        bg = self.gradient.base if self.gradient is not None else OFF_WHITE
        pygame.draw.rect(self.surface, bg, rect)
        for cell in cells:
            self._draw_cell(cell, max_distance, total_rows, show_heatmap, show_solution, solution_revealed)
        pygame.draw.rect(self.surface, BORDER_COLOR, rect, BORDER_WIDTH)

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        cols = max((c.coord.x for c in cells), default=0) + 1
        rows = max((c.coord.y for c in cells), default=0) + 1
        return pygame.Rect(
            self.offset_x, self.offset_y, cols * self.cell_size, rows * self.cell_size
        )

    def cell_at(self, pos: tuple[int, int], cells: list[Cell]) -> Coord | None:
        """Pixel → grid coord. Returns ``None`` if the click missed the maze.

        Bounds-checks against the painted maze rect rather than just floor-
        dividing, so a click in the HUD (or to the right/below the maze)
        doesn't resolve to a fictional cell off the grid.
        """
        rect = self.maze_rect(cells)
        if not rect.collidepoint(pos):
            return None
        x = (pos[0] - self.offset_x) // self.cell_size
        y = (pos[1] - self.offset_y) // self.cell_size
        return Coord(int(x), int(y))

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(
            self.offset_x + x * self.cell_size,
            self.offset_y + y * self.cell_size,
            self.cell_size,
            self.cell_size,
        )

    def _draw_cell(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
        solution_revealed: frozenset | None = None,
    ) -> None:
        rect = self._cell_rect(cell.coord.x, cell.coord.y)
        pygame.draw.rect(
            self.surface,
            cell_color(cell, max_distance, total_rows, show_heatmap, show_solution, self.palette, self.gradient, self._trail_dict, solution_revealed),
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

        if cell.is_active:
            radius = max(3, self.cell_size // 4)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, rect.center, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, rect.center, radius, max(1, w // 2))
            self._draw_open_exit_dots(rect, cell)

    def _draw_open_exit_dots(self, rect: pygame.Rect, cell: Cell) -> None:
        """Place a small white dot near each open edge of the active cell.

        Affordance to surface which moves are valid right now — same intent
        as the iOS D-pad's per-direction enabled state.
        """
        cx, cy = rect.center
        # Dot sits ~3/8 of the way from the center to the edge in the open
        # direction. Scaled to cell_size so it remains visible at small grids.
        offset = self.cell_size * 3 // 8
        dot_radius = max(2, self.cell_size // 12)
        outline = max(1, dot_radius // 2)
        for direction, (dx, dy) in ORTHO_OFFSETS.items():
            if direction not in cell.linked:
                continue
            dot = (cx + dx * offset, cy + dy * offset)
            pygame.draw.circle(self.surface, OPEN_EXIT_DOT_COLOR, dot, dot_radius)
            pygame.draw.circle(self.surface, WALL_COLOR, dot, dot_radius, outline)

    def _draw_letter(self, rect: pygame.Rect, letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=rect.center))


# --- Sigma (hexagonal) ----------------------------------------------------

def hex_offset_delta(direction: Direction, is_odd_column: bool) -> tuple[int, int] | None:
    """*Standard* coord offset for a sigma move in odd-q vertical layout.

    Returns ``None`` for non-hex directions. Ported from
    ``HexDirection.offsetDelta(isOddColumn:)`` in the iOS reference. This
    is the geometric offset assuming no boundary clamps — see
    :func:`hex_candidate_deltas` for the clamp-aware version.
    """
    if direction == Direction.UP:
        return (0, -1)
    if direction == Direction.DOWN:
        return (0, 1)
    if direction == Direction.UPPER_RIGHT:
        return (1, 0) if is_odd_column else (1, -1)
    if direction == Direction.LOWER_RIGHT:
        return (1, 1) if is_odd_column else (1, 0)
    if direction == Direction.LOWER_LEFT:
        return (-1, 1) if is_odd_column else (-1, 0)
    if direction == Direction.UPPER_LEFT:
        return (-1, 0) if is_odd_column else (-1, -1)
    return None


def hex_candidate_deltas(
    direction: Direction, col: int, row: int, height: int
) -> list[tuple[int, int]]:
    """All offsets a sigma direction could refer to, including Rust-clamp variants.

    The Rust library's ``assign_neighbors_sigma`` clamps ``north_diagonal``
    to the cell's own row at the top (for even cols) and ``south_diagonal``
    at the bottom (for odd cols). When the clamp triggers, both
    upper/lower diagonals on that side end up pointing to the same
    neighbor, and ``Cell.set_open_walls`` (via ``HashMap::find``) keeps
    only the first one — which may not be the *physically* accurate name.

    The clamp only fires on the boundary rows (top for even cols, bottom
    for odd cols). Adding the alternate offset off-boundary would make
    callers think a non-existent link exists — at non-boundary cells the
    alternate offset points to a *different* physical neighbor that
    happens to share the same direction name on neither side.
    """
    is_odd_column = (col & 1) == 1
    standard = hex_offset_delta(direction, is_odd_column)
    if standard is None:
        return []
    candidates = [standard]
    on_top_even_edge = not is_odd_column and row == 0
    on_bottom_odd_edge = is_odd_column and row == height - 1
    if direction in (Direction.UPPER_LEFT, Direction.UPPER_RIGHT) and on_top_even_edge:
        candidates.append((standard[0], 0))
    elif direction in (Direction.LOWER_LEFT, Direction.LOWER_RIGHT) and on_bottom_odd_edge:
        candidates.append((standard[0], 0))
    return candidates


# Each cell's six physical hex edges, expressed as (vertex-index pair,
# delta to the neighbor's coord). Indexed by ``is_odd_column`` because the
# odd-q-vertical layout shifts diagonal neighbors by ±1 row.
_PHYSICAL_HEX_EDGES_EVEN: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((0, 1), (0, -1)),    # UP edge
    ((1, 2), (1, -1)),    # upper-right edge
    ((2, 3), (1, 0)),     # lower-right edge
    ((3, 4), (0, 1)),     # DOWN edge
    ((4, 5), (-1, 0)),    # lower-left edge
    ((5, 0), (-1, -1)),   # upper-left edge
)

_PHYSICAL_HEX_EDGES_ODD: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((0, 1), (0, -1)),    # UP edge
    ((1, 2), (1, 0)),     # upper-right edge
    ((2, 3), (1, 1)),     # lower-right edge
    ((3, 4), (0, 1)),     # DOWN edge
    ((4, 5), (-1, 1)),    # lower-left edge
    ((5, 0), (-1, 0)),    # upper-left edge
)


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-cast point-in-polygon. Used by sigma click hit-testing."""
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def build_sigma_linked_pairs(
    cells: list[Cell], by_coord: dict[Coord, Cell]
) -> set[frozenset[Coord]]:
    """Resolve direction-name links into geometric coord pairs.

    For each direction in ``cell.linked``, walk the candidate offsets and
    pick the first one that lands on an existing cell. This makes wall
    drawing — and click-to-move direction lookup — tolerant of the Rust
    library's clamp ambiguity at top-row even-col / bottom-row odd-col
    boundaries (see ``hex_candidate_deltas`` for the full explanation).
    """
    height = max((c.coord.y for c in cells), default=0) + 1
    pairs: set[frozenset[Coord]] = set()
    for cell in cells:
        for direction in cell.linked:
            for dx, dy in hex_candidate_deltas(
                direction, cell.coord.x, cell.coord.y, height
            ):
                target = Coord(cell.coord.x + dx, cell.coord.y + dy)
                if target in by_coord:
                    pairs.add(frozenset({cell.coord, target}))
                    break
    return pairs


def sigma_direction(active: Cell, target: Coord, cells: list[Cell]) -> Direction | None:
    """Find a direction name in ``active.linked`` that connects to ``target``.

    Returns ``None`` if the target isn't actually linked from active. Reads
    the direction name straight from ``active.linked`` rather than
    reverse-mapping the coord delta — at boundary-clamp cells the FFI may
    keep the *physically wrong* name in ``linked``, but it's the name the
    Rust ``make_move`` will accept, so it's the one we have to send back.
    """
    height = max((c.coord.y for c in cells), default=0) + 1
    for direction in active.linked:
        for dx, dy in hex_candidate_deltas(direction, active.coord.x, active.coord.y, height):
            if (active.coord.x + dx, active.coord.y + dy) == (target.x, target.y):
                return direction
    return None


class SigmaRenderer:
    """Renders a sigma (flat-top hexagonal) maze onto a Pygame surface.

    Layout is odd-q vertical offset, matching the iOS reference. The
    bounding box of the painted region is
    ``(cell_size * (1.5*cols + 0.5), hex_height * (rows + 0.5))`` where
    ``hex_height = sqrt(3) * cell_size``.

    Wall drawing checks both sides of every edge: a wall is rendered only
    if neither this cell nor its neighbor lists the connecting direction
    in ``linked``. Mirrors ``SigmaCellView``'s ``!(linked || neighborLink)``
    guard — defensive against any (hypothetical) one-sided link.
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
        self.hex_height = _SQRT3 * cell_size
        # Sigma stroke denominator from MazeCellAppearance.swift.
        denom = 6 if cell_size >= 18 else 7
        self.wall_width = max(1, cell_size // denom)
        self._marker_font = pygame.font.SysFont(None, max(14, int(cell_size * 0.9)))
        self.gradient: GradientTheme | None = None

    def set_gradient(self, gradient: GradientTheme | None) -> None:
        self.gradient = gradient

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool, trail: list | None = None, solution_revealed: frozenset | None = None) -> None:
        if not cells:
            return
        self._trail_dict: dict = {coord: i for i, coord in enumerate(trail)} if trail else {}
        max_distance = max(c.distance for c in cells)
        total_rows = max(c.coord.y for c in cells) + 1
        by_coord = {c.coord: c for c in cells}
        # Precompute the set of unordered linked coord-pairs. Iterating
        # direction-name → candidate-offset → first-existing-neighbor
        # avoids the boundary-clamp pitfall where the FFI's
        # ``set_open_walls`` reports a direction name whose standard
        # offset doesn't match the physical neighbor.
        linked_pairs = build_sigma_linked_pairs(cells, by_coord)

        bbox = self.maze_rect(cells)
        bg = self.gradient.base if self.gradient is not None else OFF_WHITE
        pygame.draw.rect(self.surface, bg, bbox)

        for cell in cells:
            self._draw_cell(
                cell, by_coord, linked_pairs, max_distance, total_rows, show_heatmap, show_solution, solution_revealed
            )

        pygame.draw.rect(self.surface, BORDER_COLOR, bbox, BORDER_WIDTH)

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        cols = max((c.coord.x for c in cells), default=0) + 1
        rows = max((c.coord.y for c in cells), default=0) + 1
        width = int(round(self.cell_size * (1.5 * cols + 0.5)))
        height = int(round(self.hex_height * (rows + 0.5)))
        return pygame.Rect(self.offset_x, self.offset_y, width, height)

    def cell_at(self, pos: tuple[int, int], cells: list[Cell]) -> Coord | None:
        """Pixel → grid coord. Returns ``None`` if the click missed all hexes.

        Two-pass: pick the cell whose center is closest to the click (cheap
        Manhattan-style scan over the small grids we ship with), then verify
        the click is actually inside that hex's polygon. The verify pass
        matters because closest-center on its own can resolve a click in a
        sliver between hexes to the wrong neighbor.
        """
        if not self.maze_rect(cells).collidepoint(pos):
            return None
        px, py = pos
        best: Coord | None = None
        best_dist_sq = float("inf")
        for cell in cells:
            cx, cy = self._cell_center(cell.coord.x, cell.coord.y)
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best = cell.coord
        if best is None:
            return None
        if not _point_in_polygon((px, py), self._cell_polygon(best.x, best.y)):
            return None
        return best

    def _vertex(self, q: int, r: int, vertex_index: int) -> tuple[float, float]:
        """Absolute (x, y) of the given vertex of cell (q, r).

        Local unit vertices (in cell_size units) are::

            0: (0.5, 0)     1: (1.5, 0)     2: (2,   h/2)
            5: (0,   h/2)                   3: (1.5, h)
                            4: (0.5, h)
        """
        # Local vertex offsets from the cell's bounding-rect origin.
        local = (
            (0.5, 0.0),
            (1.5, 0.0),
            (2.0, _SQRT3 / 2),
            (1.5, _SQRT3),
            (0.5, _SQRT3),
            (0.0, _SQRT3 / 2),
        )[vertex_index]
        # Cell bounding-rect origin in absolute coords. Odd columns shift
        # down by half a hex (odd-q vertical offset).
        q_odd_shift = self.hex_height / 2 if (q & 1) == 1 else 0.0
        origin_x = self.offset_x + self.cell_size * 1.5 * q
        origin_y = self.offset_y + self.hex_height * r + q_odd_shift
        return (origin_x + local[0] * self.cell_size, origin_y + local[1] * self.cell_size)

    def _cell_polygon(self, q: int, r: int) -> list[tuple[float, float]]:
        return [self._vertex(q, r, i) for i in range(6)]

    def _cell_center(self, q: int, r: int) -> tuple[float, float]:
        q_odd_shift = self.hex_height / 2 if (q & 1) == 1 else 0.0
        cx = self.offset_x + self.cell_size * (1.5 * q + 1)
        cy = self.offset_y + self.hex_height * (r + 0.5) + q_odd_shift
        return (cx, cy)

    def _draw_cell(
        self,
        cell: Cell,
        by_coord: dict[Coord, Cell],
        linked_pairs: set[frozenset[Coord]],
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
        solution_revealed: frozenset | None = None,
    ) -> None:
        q, r = cell.coord.x, cell.coord.y
        polygon = self._cell_polygon(q, r)
        pygame.draw.polygon(
            self.surface,
            cell_color(cell, max_distance, total_rows, show_heatmap, show_solution, self.palette, self.gradient, self._trail_dict, solution_revealed),
            polygon,
        )

        # Iterate physical edges: for each edge, the geometry tells us which
        # neighbor coord it abuts. Skip the wall iff that pair is in
        # ``linked_pairs``. Geometry-driven, so the Rust direction-name
        # clamp at corners doesn't produce visual artifacts here.
        edges = _PHYSICAL_HEX_EDGES_ODD if (q & 1) == 1 else _PHYSICAL_HEX_EDGES_EVEN
        for (i, j), (dx, dy) in edges:
            neighbor_coord = Coord(q + dx, r + dy)
            if neighbor_coord in by_coord and frozenset({cell.coord, neighbor_coord}) in linked_pairs:
                continue
            pygame.draw.line(self.surface, WALL_COLOR, polygon[i], polygon[j], self.wall_width)

        center = self._cell_center(q, r)
        center_int = (int(round(center[0])), int(round(center[1])))

        if cell.is_active:
            radius = max(3, self.cell_size // 3)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, center_int, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, center_int, radius, max(1, self.wall_width // 2))
            self._draw_open_exit_dots(cell, center, polygon, by_coord, total_rows)

    def _draw_open_exit_dots(
        self,
        cell: Cell,
        center: tuple[float, float],
        polygon: list[tuple[float, float]],
        by_coord: dict[Coord, Cell],
        height: int,
    ) -> None:
        """Place a dot near each open hex edge of the active cell.

        Resolves each direction in ``cell.linked`` to its physical neighbor
        coord (handling the boundary clamp via ``hex_candidate_deltas``) so
        the dot always lands on the correct edge — not on the edge whose
        name happens to be in ``linked`` after the FFI's clamp collision.
        """
        is_odd = (cell.coord.x & 1) == 1
        edges = _PHYSICAL_HEX_EDGES_ODD if is_odd else _PHYSICAL_HEX_EDGES_EVEN
        # Map physical neighbor delta → vertex pair, so once we know the
        # target neighbor, we know which edge midpoint to mark.
        edge_by_delta = {(dx, dy): (i, j) for (i, j), (dx, dy) in edges}
        cx, cy = center
        dot_radius = max(2, self.cell_size // 12)
        outline = max(1, dot_radius // 2)
        seen_edges: set[tuple[int, int]] = set()
        for direction in cell.linked:
            for dx, dy in hex_candidate_deltas(direction, cell.coord.x, cell.coord.y, height):
                if Coord(cell.coord.x + dx, cell.coord.y + dy) in by_coord:
                    edge = edge_by_delta.get((dx, dy))
                    if edge is None or edge in seen_edges:
                        break
                    seen_edges.add(edge)
                    i, j = edge
                    mx = (polygon[i][0] + polygon[j][0]) / 2
                    my = (polygon[i][1] + polygon[j][1]) / 2
                    # Pull the dot ~60% of the way out from the center to
                    # the edge midpoint — visible against the active marker
                    # without crowding the wall.
                    pos = (cx + 0.6 * (mx - cx), cy + 0.6 * (my - cy))
                    pygame.draw.circle(self.surface, OPEN_EXIT_DOT_COLOR, pos, dot_radius)
                    pygame.draw.circle(self.surface, WALL_COLOR, pos, dot_radius, outline)
                    break

    def _draw_letter(self, center: tuple[int, int], letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=center))


# --- Delta (triangular) ---------------------------------------------------


def delta_direction(active: Cell, target: Coord) -> Direction | None:
    """Find the direction in ``active.linked`` that connects to ``target``.

    Delta neighbor mapping is unambiguous (no boundary-clamp issue):
      Normal cell  (col+row even): UpperLeft=(-1,0), UpperRight=(+1,0), Down=(0,+1).
      Inverted cell (col+row odd): LowerLeft=(-1,0), LowerRight=(+1,0), Up=(0,-1).
    We look up the coord delta and return the matching direction only if it
    appears in ``active.linked``.
    """
    col, row = active.coord.x, active.coord.y
    dx, dy = target.x - col, target.y - row
    is_normal = (col + row) % 2 == 0
    mapping: dict[tuple[int, int], Direction]
    if is_normal:
        mapping = {(-1, 0): Direction.UPPER_LEFT, (1, 0): Direction.UPPER_RIGHT, (0, 1): Direction.DOWN}
    else:
        mapping = {(-1, 0): Direction.LOWER_LEFT, (1, 0): Direction.LOWER_RIGHT, (0, -1): Direction.UP}
    direction = mapping.get((dx, dy))
    if direction is None or direction not in active.linked:
        return None
    return direction


class DeltaRenderer:
    """Renders a delta (equilateral-triangle) maze onto a Pygame surface.

    Each cell is an equilateral triangle. Normal cells (``(col+row) % 2 == 0``)
    point upward; Inverted cells point downward. Adjacent cells share a
    ``cell_size / 2`` horizontal overlap, matching the iOS HStack layout.

    Bounding box: ``cell_size * (cols + 1) / 2`` wide,
    ``tri_height * rows`` tall (ported from ``DeltaMazeView``).
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
        self.tri_height = _SQRT3 / 2 * cell_size
        # Delta wall stroke from iOS MazeCellAppearance.swift:
        # denominator 10 at cell_size>=28, else 12, multiplied by 1.15.
        denom = 10 if cell_size >= 28 else 12
        self.wall_width = max(1, int(round(cell_size / denom * 1.15)))
        self._marker_font = pygame.font.SysFont(None, max(12, int(cell_size * 0.7)))
        self.gradient: GradientTheme | None = None

    def set_gradient(self, gradient: GradientTheme | None) -> None:
        self.gradient = gradient

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        cols = max(c.coord.x for c in cells) + 1
        rows = max(c.coord.y for c in cells) + 1
        w = int(round(self.cell_size * (cols + 1) / 2))
        h = int(round(self.tri_height * rows))
        return pygame.Rect(self.offset_x, self.offset_y, w, h)

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool, trail: list | None = None, solution_revealed: frozenset | None = None) -> None:
        if not cells:
            return
        self._trail_dict: dict = {coord: i for i, coord in enumerate(trail)} if trail else {}
        max_distance = max(c.distance for c in cells)
        total_rows = max(c.coord.y for c in cells) + 1
        bbox = self.maze_rect(cells)
        bg = self.gradient.base if self.gradient is not None else OFF_WHITE
        pygame.draw.rect(self.surface, bg, bbox)
        for cell in cells:
            self._draw_cell(cell, max_distance, total_rows, show_heatmap, show_solution, solution_revealed)
        pygame.draw.rect(self.surface, BORDER_COLOR, bbox, BORDER_WIDTH)

    def cell_at(self, pos: tuple[int, int], cells: list[Cell]) -> Coord | None:
        """Pixel → grid coord. Returns ``None`` if the click missed all triangles."""
        if not self.maze_rect(cells).collidepoint(pos):
            return None
        px, py = pos
        best: Coord | None = None
        best_dist_sq = float("inf")
        for cell in cells:
            cx, cy = self._cell_center(cell.coord.x, cell.coord.y)
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best = cell.coord
        if best is None:
            return None
        if not _point_in_polygon((px, py), self._cell_polygon(best.x, best.y)):
            return None
        return best

    def _cell_polygon(self, col: int, row: int) -> list[tuple[float, float]]:
        """Three vertices of the triangle at (col, row)."""
        x0 = self.offset_x + col * self.cell_size / 2
        y0 = self.offset_y + row * self.tri_height
        cs = self.cell_size
        th = self.tri_height
        if (col + row) % 2 == 0:
            # Normal: apex at top
            return [(x0 + cs / 2, y0), (x0, y0 + th), (x0 + cs, y0 + th)]
        else:
            # Inverted: apex at bottom
            return [(x0, y0), (x0 + cs, y0), (x0 + cs / 2, y0 + th)]

    def _cell_center(self, col: int, row: int) -> tuple[float, float]:
        poly = self._cell_polygon(col, row)
        return (sum(p[0] for p in poly) / 3, sum(p[1] for p in poly) / 3)

    def _draw_cell(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
        solution_revealed: frozenset | None = None,
    ) -> None:
        col, row = cell.coord.x, cell.coord.y
        is_normal = (col + row) % 2 == 0
        polygon = self._cell_polygon(col, row)

        pygame.draw.polygon(
            self.surface,
            cell_color(cell, max_distance, total_rows, show_heatmap, show_solution, self.palette, self.gradient, self._trail_dict, solution_revealed),
            polygon,
        )

        w = self.wall_width
        if is_normal:
            if Direction.UPPER_LEFT not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[0], polygon[1], w)
            if Direction.UPPER_RIGHT not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[0], polygon[2], w)
            if Direction.DOWN not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[1], polygon[2], w)
        else:
            if Direction.UP not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[0], polygon[1], w)
            if Direction.LOWER_LEFT not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[0], polygon[2], w)
            if Direction.LOWER_RIGHT not in cell.linked:
                pygame.draw.line(self.surface, WALL_COLOR, polygon[1], polygon[2], w)

        center = self._cell_center(col, row)
        center_int = (int(round(center[0])), int(round(center[1])))

        if cell.is_active:
            radius = max(2, self.cell_size // 5)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, center_int, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, center_int, radius, max(1, w // 2))
            self._draw_open_exit_dots(cell, center, polygon, is_normal)

    def _draw_open_exit_dots(
        self,
        cell: Cell,
        center: tuple[float, float],
        polygon: list[tuple[float, float]],
        is_normal: bool,
    ) -> None:
        cx, cy = center
        dot_radius = max(2, self.cell_size // 12)
        outline = max(1, dot_radius // 2)
        edges: list[tuple[Direction, tuple[float, float], tuple[float, float]]]
        if is_normal:
            edges = [
                (Direction.UPPER_LEFT, polygon[0], polygon[1]),
                (Direction.UPPER_RIGHT, polygon[0], polygon[2]),
                (Direction.DOWN, polygon[1], polygon[2]),
            ]
        else:
            edges = [
                (Direction.UP, polygon[0], polygon[1]),
                (Direction.LOWER_LEFT, polygon[0], polygon[2]),
                (Direction.LOWER_RIGHT, polygon[1], polygon[2]),
            ]
        for direction, va, vb in edges:
            if direction not in cell.linked:
                continue
            mx = (va[0] + vb[0]) / 2
            my = (va[1] + vb[1]) / 2
            pos = (cx + 0.6 * (mx - cx), cy + 0.6 * (my - cy))
            pygame.draw.circle(self.surface, OPEN_EXIT_DOT_COLOR, pos, dot_radius)
            pygame.draw.circle(self.surface, WALL_COLOR, pos, dot_radius, outline)

    def _draw_letter(self, center: tuple[int, int], letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=center))


# --- Rhombic (diamond) ----------------------------------------------------

# Coord offsets for the four diagonal Rhombic directions.
# The Rust assigns these via assign_neighbors_rhombic; no boundary-clamp
# ambiguity (unlike Sigma) — each direction maps to exactly one delta.
RHOMBIC_OFFSETS: dict[Direction, tuple[int, int]] = {
    Direction.UPPER_RIGHT: (1, -1),
    Direction.LOWER_RIGHT: (1, 1),
    Direction.LOWER_LEFT: (-1, 1),
    Direction.UPPER_LEFT: (-1, -1),
}


def rhombic_direction(active: Cell, target: Coord) -> Direction | None:
    """Find the direction in ``active.linked`` that connects to ``target``.

    Rhombic has four diagonal directions, each with an unambiguous coord
    delta (no boundary-clamp issue).  Returns ``None`` if ``target`` is not
    a linked neighbor of ``active``.
    """
    dx, dy = target.x - active.coord.x, target.y - active.coord.y
    direction = {v: k for k, v in RHOMBIC_OFFSETS.items()}.get((dx, dy))
    if direction is None or direction not in active.linked:
        return None
    return direction


_SQRT2 = math.sqrt(2)


class RhombicRenderer:
    """Renders a rhombic (45°-rotated diamond) maze onto a Pygame surface.

    Only cells where ``(col + row) % 2 == 0`` are rendered — the underlying
    grid is a checkerboard pattern.  Cell (col, row) has its top vertex at
    ``(offset_x + col * half_diagonal, offset_y + row * half_diagonal)``
    where ``half_diagonal = cell_size * sqrt(2) / 2``.

    Bounding box: ``half_diagonal * max_x + diagonal`` wide,
    ``half_diagonal * max_y + diagonal`` tall
    (ported from ``RhombicMazeView.containerWidth/Height``).
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
        self.diagonal = cell_size * _SQRT2
        self.half_diagonal = self.diagonal / 2
        # Wall stroke from iOS MazeCellAppearance.swift wallStrokeWidth(for:.rhombic)
        denom = 7.0 if cell_size >= 18 else 4.8
        self.wall_width = max(1, int(round(cell_size / denom)))
        self._marker_font = pygame.font.SysFont(None, max(14, int(cell_size * 0.9)))
        self.gradient: GradientTheme | None = None

    def set_gradient(self, gradient: GradientTheme | None) -> None:
        self.gradient = gradient

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        valid = [c for c in cells if (c.coord.x + c.coord.y) % 2 == 0]
        if not valid:
            return pygame.Rect(self.offset_x, self.offset_y, 0, 0)
        max_x = max(c.coord.x for c in valid)
        max_y = max(c.coord.y for c in valid)
        w = int(round(self.half_diagonal * max_x + self.diagonal))
        h = int(round(self.half_diagonal * max_y + self.diagonal))
        return pygame.Rect(self.offset_x, self.offset_y, w, h)

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool, trail: list | None = None, solution_revealed: frozenset | None = None) -> None:
        valid = [c for c in cells if (c.coord.x + c.coord.y) % 2 == 0]
        if not valid:
            return
        self._trail_dict: dict = {coord: i for i, coord in enumerate(trail)} if trail else {}
        max_distance = max(c.distance for c in valid)
        total_rows = max(c.coord.y for c in valid) + 1
        bbox = self.maze_rect(valid)
        bg = self.gradient.base if self.gradient is not None else OFF_WHITE
        pygame.draw.rect(self.surface, bg, bbox)
        for cell in valid:
            self._draw_cell(cell, max_distance, total_rows, show_heatmap, show_solution, solution_revealed)
        pygame.draw.rect(self.surface, BORDER_COLOR, bbox, BORDER_WIDTH)

    def cell_at(self, pos: tuple[int, int], cells: list[Cell]) -> Coord | None:
        """Pixel → grid coord. Returns ``None`` if the click missed all diamonds."""
        valid = [c for c in cells if (c.coord.x + c.coord.y) % 2 == 0]
        if not valid or not self.maze_rect(valid).collidepoint(pos):
            return None
        px, py = pos
        best: Coord | None = None
        best_dist_sq = float("inf")
        for cell in valid:
            cx, cy = self._cell_center(cell.coord.x, cell.coord.y)
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best = cell.coord
        if best is None:
            return None
        if not _point_in_polygon((px, py), self._cell_polygon(best.x, best.y)):
            return None
        return best

    def _cell_center(self, col: int, row: int) -> tuple[float, float]:
        # Top vertex of the diamond is at (col*hd, row*hd); center is box/2 further.
        x0 = self.offset_x + col * self.half_diagonal
        y0 = self.offset_y + row * self.half_diagonal
        return (x0 + self.diagonal / 2, y0 + self.diagonal / 2)

    def _cell_polygon(self, col: int, row: int) -> list[tuple[float, float]]:
        """Four vertices of the diamond at (col, row): top, right, bottom, left."""
        x0 = self.offset_x + col * self.half_diagonal
        y0 = self.offset_y + row * self.half_diagonal
        b = self.diagonal
        return [
            (x0 + b / 2, y0),          # top
            (x0 + b,     y0 + b / 2),  # right
            (x0 + b / 2, y0 + b),      # bottom
            (x0,         y0 + b / 2),  # left
        ]

    def _draw_cell(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
        solution_revealed: frozenset | None = None,
    ) -> None:
        col, row = cell.coord.x, cell.coord.y
        polygon = self._cell_polygon(col, row)
        pygame.draw.polygon(
            self.surface,
            cell_color(
                cell, max_distance, total_rows, show_heatmap, show_solution,
                self.palette, self.gradient, self._trail_dict, solution_revealed,
            ),
            polygon,
        )

        w = self.wall_width
        # Edges: UpperRight=0→1, LowerRight=1→2, LowerLeft=2→3, UpperLeft=3→0
        if Direction.UPPER_RIGHT not in cell.linked:
            pygame.draw.line(self.surface, WALL_COLOR, polygon[0], polygon[1], w)
        if Direction.LOWER_RIGHT not in cell.linked:
            pygame.draw.line(self.surface, WALL_COLOR, polygon[1], polygon[2], w)
        if Direction.LOWER_LEFT not in cell.linked:
            pygame.draw.line(self.surface, WALL_COLOR, polygon[2], polygon[3], w)
        if Direction.UPPER_LEFT not in cell.linked:
            pygame.draw.line(self.surface, WALL_COLOR, polygon[3], polygon[0], w)

        center = self._cell_center(col, row)
        center_int = (int(round(center[0])), int(round(center[1])))

        if cell.is_active:
            radius = max(3, self.cell_size // 3)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, center_int, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, center_int, radius, max(1, w // 2))
            self._draw_open_exit_dots(cell, center, polygon)

    def _draw_open_exit_dots(
        self,
        cell: Cell,
        center: tuple[float, float],
        polygon: list[tuple[float, float]],
    ) -> None:
        cx, cy = center
        dot_radius = max(2, self.cell_size // 12)
        outline = max(1, dot_radius // 2)
        # Edge midpoint per direction: same vertex-pair as wall drawing.
        edge_midpoints = {
            Direction.UPPER_RIGHT: ((polygon[0][0] + polygon[1][0]) / 2,
                                    (polygon[0][1] + polygon[1][1]) / 2),
            Direction.LOWER_RIGHT: ((polygon[1][0] + polygon[2][0]) / 2,
                                    (polygon[1][1] + polygon[2][1]) / 2),
            Direction.LOWER_LEFT:  ((polygon[2][0] + polygon[3][0]) / 2,
                                    (polygon[2][1] + polygon[3][1]) / 2),
            Direction.UPPER_LEFT:  ((polygon[3][0] + polygon[0][0]) / 2,
                                    (polygon[3][1] + polygon[0][1]) / 2),
        }
        for direction, (mx, my) in edge_midpoints.items():
            if direction not in cell.linked:
                continue
            pos = (cx + 0.6 * (mx - cx), cy + 0.6 * (my - cy))
            pygame.draw.circle(self.surface, OPEN_EXIT_DOT_COLOR, pos, dot_radius)
            pygame.draw.circle(self.surface, WALL_COLOR, pos, dot_radius, outline)

    def _draw_letter(self, center: tuple[int, int], letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=center))


# --- Upsilon (octagon + square) -------------------------------------------

# Eight-direction coord offsets for Upsilon. Both octagons and squares share
# the same coordinate system; squares simply never link diagonally.
UPSILON_OFFSETS: dict[Direction, tuple[int, int]] = {
    Direction.UP:          (0, -1),
    Direction.RIGHT:       (1,  0),
    Direction.DOWN:        (0,  1),
    Direction.LEFT:        (-1, 0),
    Direction.UPPER_RIGHT: (1, -1),
    Direction.LOWER_RIGHT: (1,  1),
    Direction.LOWER_LEFT:  (-1, 1),
    Direction.UPPER_LEFT:  (-1, -1),
}

_UPSILON_OFFSET_TO_DIR: dict[tuple[int, int], Direction] = {
    v: k for k, v in UPSILON_OFFSETS.items()
}

# Octagon edge list: (direction, vertex_i, vertex_j).  Ported from
# UpsilonCellView.swift WallView body (octagon branch).
_OCTAGON_EDGES: tuple[tuple[Direction, int, int], ...] = (
    (Direction.UP,          0, 1),
    (Direction.UPPER_RIGHT, 1, 2),
    (Direction.RIGHT,       2, 3),
    (Direction.LOWER_RIGHT, 3, 4),
    (Direction.DOWN,        4, 5),
    (Direction.LOWER_LEFT,  5, 6),
    (Direction.LEFT,        6, 7),
    (Direction.UPPER_LEFT,  7, 0),
)

# Square edge list: (direction, vertex_i, vertex_j).
_SQUARE_EDGES: tuple[tuple[Direction, int, int], ...] = (
    (Direction.UP,    0, 1),
    (Direction.RIGHT, 1, 2),
    (Direction.DOWN,  2, 3),
    (Direction.LEFT,  3, 0),
)


def upsilon_direction(active: Cell, target: Coord) -> Direction | None:
    """Find the direction in ``active.linked`` that connects to ``target``.

    Upsilon coord deltas are unambiguous (no boundary-clamp issue, unlike
    Sigma). Squares only link cardinally; octagons may link in all eight
    directions. Returns ``None`` if target is not a linked neighbor.
    """
    dx, dy = target.x - active.coord.x, target.y - active.coord.y
    direction = _UPSILON_OFFSET_TO_DIR.get((dx, dy))
    if direction is None or direction not in active.linked:
        return None
    return direction


class UpsilonRenderer:
    """Renders an upsilon (octagon + square alternating) maze onto a Pygame surface.

    Each grid position holds either an octagon (``(col+row) % 2 == 0``) or a
    square (``(col+row) % 2 == 1``). Both share the same center-to-center
    step ``cell_size * sqrt(2) / 2``, matching the iOS ``LazyVGrid`` layout
    (horizontal spacing ``-(octagonSize - squareSize) / 2``, frame height
    ``octagonSize * sqrt(2) / 2``).  The octagon overflows its frame slot
    vertically by ~14.6% of cell_size; adjacent-row octagons share that
    overlap, which is why iOS uses ``verticalSpacing = -1`` (sub-pixel).

    Ported from ``UpsilonCellView.swift`` / ``UpsilonMazeView.swift`` with
    geometry from ``MazeLayoutMetrics.swift``.
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
        # squareSize from MazeLayoutMetrics: octagonSize * (sqrt(2) - 1)
        self.square_size = cell_size * (_SQRT2 - 1)
        # Center-to-center distance between adjacent cells (H and V).
        self.step = cell_size * _SQRT2 / 2
        # Octagon geometry: r = half cell_size, k = 2r / (2 + sqrt(2)).
        r = cell_size / 2
        self._r = r
        self._k = 2.0 * r / (2.0 + _SQRT2)
        # Wall stroke from iOS wallStrokeWidth(for:.upsilon): denom 12 at >=28, else 16.
        denom = 12 if cell_size >= 28 else 16
        self.wall_width = max(1, int(round(cell_size / denom)))
        self._marker_font = pygame.font.SysFont(None, max(14, int(cell_size * 0.9)))
        self.gradient: GradientTheme | None = None

    def set_gradient(self, gradient: GradientTheme | None) -> None:
        self.gradient = gradient

    def maze_rect(self, cells: list[Cell]) -> pygame.Rect:
        cols = max(c.coord.x for c in cells) + 1
        rows = max(c.coord.y for c in cells) + 1
        w = int(round((cols - 1) * self.step + self.cell_size))
        h = int(round((rows - 1) * self.step + self.cell_size))
        return pygame.Rect(self.offset_x, self.offset_y, w, h)

    def draw(self, cells: list[Cell], show_heatmap: bool, show_solution: bool, trail: list | None = None, solution_revealed: frozenset | None = None) -> None:
        if not cells:
            return
        self._trail_dict: dict = {coord: i for i, coord in enumerate(trail)} if trail else {}
        max_distance = max(c.distance for c in cells)
        total_rows = max(c.coord.y for c in cells) + 1
        bbox = self.maze_rect(cells)
        bg = self.gradient.base if self.gradient is not None else OFF_WHITE
        pygame.draw.rect(self.surface, bg, bbox)
        for cell in cells:
            self._draw_cell(cell, max_distance, total_rows, show_heatmap, show_solution, solution_revealed)
        pygame.draw.rect(self.surface, BORDER_COLOR, bbox, BORDER_WIDTH)

    def cell_at(self, pos: tuple[int, int], cells: list[Cell]) -> Coord | None:
        """Pixel → grid coord. Returns ``None`` if the click missed all cells.

        Two-pass: closest center then point-in-polygon. The polygon check
        is essential because the octagon fill overflows its step-box and
        closest-center alone would mis-assign clicks in the overlap band.
        """
        if not self.maze_rect(cells).collidepoint(pos):
            return None
        px, py = pos
        best: Coord | None = None
        best_dist_sq = float("inf")
        for cell in cells:
            cx, cy = self._cell_center(cell.coord.x, cell.coord.y)
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best = cell.coord
        if best is None:
            return None
        if not _point_in_polygon((px, py), self._cell_polygon(best.x, best.y)):
            return None
        return best

    def _cell_center(self, col: int, row: int) -> tuple[float, float]:
        return (
            self.offset_x + col * self.step + self.cell_size / 2,
            self.offset_y + row * self.step + self.cell_size / 2,
        )

    def _octagon_points(self, cx: float, cy: float) -> list[tuple[float, float]]:
        r, k = self._r, self._k
        return [
            (cx - r + k, cy - r),   # 0: top-left of top edge
            (cx + r - k, cy - r),   # 1: top-right of top edge
            (cx + r,     cy - r + k),  # 2: right-top
            (cx + r,     cy + r - k),  # 3: right-bottom
            (cx + r - k, cy + r),   # 4: bottom-right of bottom edge
            (cx - r + k, cy + r),   # 5: bottom-left of bottom edge
            (cx - r,     cy + r - k),  # 6: left-bottom
            (cx - r,     cy - r + k),  # 7: left-top
        ]

    def _square_points(self, cx: float, cy: float) -> list[tuple[float, float]]:
        s = self.square_size / 2
        return [
            (cx - s, cy - s),  # 0: top-left
            (cx + s, cy - s),  # 1: top-right
            (cx + s, cy + s),  # 2: bottom-right
            (cx - s, cy + s),  # 3: bottom-left
        ]

    def _cell_polygon(self, col: int, row: int) -> list[tuple[float, float]]:
        cx, cy = self._cell_center(col, row)
        if (col + row) % 2 == 1:
            return self._square_points(cx, cy)
        return self._octagon_points(cx, cy)

    def _draw_cell(
        self,
        cell: Cell,
        max_distance: int,
        total_rows: int,
        show_heatmap: bool,
        show_solution: bool,
        solution_revealed: frozenset | None = None,
    ) -> None:
        col, row = cell.coord.x, cell.coord.y
        is_sq = (col + row) % 2 == 1
        cx, cy = self._cell_center(col, row)
        center_int = (int(round(cx)), int(round(cy)))

        polygon = self._cell_polygon(col, row)
        pygame.draw.polygon(
            self.surface,
            cell_color(
                cell, max_distance, total_rows, show_heatmap, show_solution,
                self.palette, self.gradient, self._trail_dict, solution_revealed,
            ),
            polygon,
        )

        w = self.wall_width
        if is_sq:
            pts = self._square_points(cx, cy)
            for direction, i, j in _SQUARE_EDGES:
                if direction not in cell.linked:
                    pygame.draw.line(self.surface, WALL_COLOR, pts[i], pts[j], w)
        else:
            pts = self._octagon_points(cx, cy)
            for direction, i, j in _OCTAGON_EDGES:
                if direction not in cell.linked:
                    pygame.draw.line(self.surface, WALL_COLOR, pts[i], pts[j], w)

        if cell.is_active:
            radius = max(3, self.cell_size // 4)
            pygame.draw.circle(self.surface, ACTIVE_MARKER_COLOR, center_int, radius)
            pygame.draw.circle(self.surface, WALL_COLOR, center_int, radius, max(1, w // 2))
            self._draw_open_exit_dots(cell, (cx, cy), is_sq)

    def _draw_open_exit_dots(
        self,
        cell: Cell,
        center: tuple[float, float],
        is_sq: bool,
    ) -> None:
        cx, cy = center
        dot_radius = max(2, self.cell_size // 12)
        outline = max(1, dot_radius // 2)
        if is_sq:
            pts = self._square_points(cx, cy)
            edge_midpoints = {
                d: ((pts[i][0] + pts[j][0]) / 2, (pts[i][1] + pts[j][1]) / 2)
                for d, i, j in _SQUARE_EDGES
            }
        else:
            pts = self._octagon_points(cx, cy)
            edge_midpoints = {
                d: ((pts[i][0] + pts[j][0]) / 2, (pts[i][1] + pts[j][1]) / 2)
                for d, i, j in _OCTAGON_EDGES
            }
        for direction, (mx, my) in edge_midpoints.items():
            if direction not in cell.linked:
                continue
            pos = (cx + 0.6 * (mx - cx), cy + 0.6 * (my - cy))
            pygame.draw.circle(self.surface, OPEN_EXIT_DOT_COLOR, pos, dot_radius)
            pygame.draw.circle(self.surface, WALL_COLOR, pos, dot_radius, outline)

    def _draw_letter(self, center: tuple[int, int], letter: str) -> None:
        text = self._marker_font.render(letter, True, LETTER_COLOR)
        self.surface.blit(text, text.get_rect(center=center))


# --- Dispatch -------------------------------------------------------------


def make_renderer(
    maze_type: MazeType,
    surface: pygame.Surface,
    cell_size: int,
    offset: tuple[int, int] = (0, 0),
    palette=HEATMAP_BELIZE_HOLE,
):
    """Return the renderer matching a maze type. Raises for unimplemented types.

    Orthogonal, Sigma, Delta, and Rhombic are implemented. Upsilon raises
    ``NotImplementedError`` rather than silently falling back.
    """
    if maze_type == MazeType.ORTHOGONAL:
        return OrthogonalRenderer(surface, cell_size, offset=offset, palette=palette)
    if maze_type == MazeType.SIGMA:
        return SigmaRenderer(surface, cell_size, offset=offset, palette=palette)
    if maze_type == MazeType.DELTA:
        return DeltaRenderer(surface, cell_size, offset=offset, palette=palette)
    if maze_type == MazeType.RHOMBIC:
        return RhombicRenderer(surface, cell_size, offset=offset, palette=palette)
    if maze_type == MazeType.UPSILON:
        return UpsilonRenderer(surface, cell_size, offset=offset, palette=palette)
    raise NotImplementedError(f"No renderer implemented for {maze_type.value}")


# Back-compat: existing callers still reference ``Renderer`` for the
# orthogonal renderer. Keep the alias rather than churning every import.
Renderer = OrthogonalRenderer


__all__ = [
    "DeltaRenderer",
    "GradientTheme",
    "HEATMAP_BELIZE_HOLE",
    "OFF_WHITE",
    "ORTHO_OFFSETS",
    "OrthogonalRenderer",
    "RHOMBIC_OFFSETS",
    "Renderer",
    "RhombicRenderer",
    "SigmaRenderer",
    "UPSILON_OFFSETS",
    "UpsilonRenderer",
    "build_sigma_linked_pairs",
    "cell_color",
    "delta_direction",
    "generate_gradient",
    "hex_candidate_deltas",
    "hex_offset_delta",
    "make_renderer",
    "orthogonal_direction",
    "rhombic_direction",
    "sigma_direction",
    "upsilon_direction",
]
