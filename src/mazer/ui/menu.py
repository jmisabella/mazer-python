"""In-game main-menu modal overlay.

``MenuState`` is a pure data class — no pygame drawing, no FFI calls.  It
handles keyboard and click events and returns ``(menu_open, request_or_None)``
from every handler so the caller can act without inspecting internal state:

* ``(True,  None)``         — stay open, nothing to apply.
* ``(False, None)``         — Esc: close, keep current maze.
* ``(False, MazeRequest)``  — Generate confirmed: close and apply new request.

If the Rust library rejects the chosen combination (returns NULL), the caller
catches ``MazeGenerationError`` and calls ``state.set_generation_error()``
which re-opens the menu with an inline message pointing the user to change
the algorithm.

``draw_menu(surface, state, font)`` renders the overlay directly into the
supplied surface and returns a ``MenuLayout`` so the caller can forward
``MOUSEBUTTONDOWN`` events to ``state.handle_click(pos, layout)`` without
re-deriving geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from mazer.types import Algorithm, Coord, MazeRequest, MazeType

# ---------------------------------------------------------------------------
# Palette — dark mode
# ---------------------------------------------------------------------------

_OVERLAY_RGBA      = (0, 0, 0, 180)

_PANEL_BG          = (22, 24, 30)
_PANEL_BORDER      = (55, 65, 85)

_FOCUSED_BG        = (35, 45, 70)

_TITLE_COLOR       = (220, 225, 240)
_LABEL_COLOR       = (140, 150, 175)
_VALUE_COLOR       = (235, 238, 248)

_ARROW_IDLE        = (75, 85, 115)
_ARROW_ACTIVE      = (110, 145, 255)

_BTN_COLOR         = (65, 115, 225)
_BTN_FOCUSED       = (85, 135, 245)
_BTN_PRESSED       = (40, 80, 165)
_BTN_TEXT          = (255, 255, 255)
_BTN_PRESSED_TEXT  = (200, 215, 255)

_DESC_BRIGHT       = (195, 205, 225)   # description text when row focused
_DESC_DIM          = (95, 105, 130)    # description text when row unfocused

_ERROR_COLOR       = (255, 85, 85)
_ANIM_NOTE_COLOR   = (110, 155, 255)

# ---------------------------------------------------------------------------
# Human-readable algorithm display names  (from MazeAlgorithm.swift displayName)
# ---------------------------------------------------------------------------

_ALGO_DISPLAY_NAME: dict[Algorithm, str] = {
    Algorithm.ALDOUS_BRODER:          "Aldous Broder",
    Algorithm.BINARY_TREE:            "Binary Tree",
    Algorithm.ELLERS:                 "Eller's",
    Algorithm.GROWING_TREE_NEWEST:    "Growing Tree (Newest)",
    Algorithm.GROWING_TREE_RANDOM:    "Growing Tree (Random)",
    Algorithm.HUNT_AND_KILL:          "Hunt and Kill",
    Algorithm.KRUSKALS:               "Kruskal's",
    Algorithm.PRIMS:                  "Prim's",
    Algorithm.RECURSIVE_BACKTRACKER:  "Recursive Backtracker",
    Algorithm.RECURSIVE_DIVISION:     "Recursive Division",
    Algorithm.REVERSE_DELETE:         "Reverse Delete",
    Algorithm.SIDEWINDER:             "Sidewinder",
    Algorithm.WILSONS:                "Wilson's",
}

# ---------------------------------------------------------------------------
# Educational descriptions  (exact text from MazeType.swift / MazeAlgorithm.swift)
# ---------------------------------------------------------------------------

_TYPE_DESC: dict[MazeType, str] = {
    MazeType.ORTHOGONAL: "Orthogonal mazes carve a classic square-grid layout with straight paths and right-angle turns.",
    MazeType.SIGMA:      "Hexagonal cells forming a web of interconnected paths, promoting more intuitive navigation.",
    MazeType.DELTA:      "Triangular cells (normal and inverted) creating jagged, complex paths.",
    MazeType.RHOMBIC:    "Diamond cells forming a grid with slanted paths.",
    MazeType.UPSILON:    "Alternating octagon and square cells add variety to pathfinding.",
}

_ALGO_DESC: dict[Algorithm, str] = {
    Algorithm.ALDOUS_BRODER:
        "This algorithm performs a random walk over the grid, carving a passage whenever it "
        "encounters an unvisited cell. It produces an unbiased maze, though it can be "
        "inefficient because it may visit cells many times.",
    Algorithm.BINARY_TREE:
        "This method iterates through each cell in a grid, carving passages either north or "
        "east (or in another fixed pair of directions). The result is a maze with a predictable "
        "bias and long, straight corridors.",
    Algorithm.ELLERS:
        "Eller's algorithm builds the maze row by row, randomly joining cells within each row "
        "and ensuring connectivity to the next row. It produces mazes with a row-wise structure "
        "and is memory-efficient for infinite mazes.",
    Algorithm.GROWING_TREE_NEWEST:
        "This algorithm maintains a list of active cells, always choosing the newest one to "
        "carve a passage to an unvisited neighbor. It can mimic other algorithms like "
        "Recursive Backtracker.",
    Algorithm.GROWING_TREE_RANDOM:
        "This algorithm maintains a list of active cells, choosing one randomly to carve a "
        "passage to an unvisited neighbor. It can mimic other algorithms like "
        "Recursive Backtracker.",
    Algorithm.HUNT_AND_KILL:
        "Combining random walks with systematic scanning, this method randomly carves a passage "
        "until it reaches a dead end, then 'hunts' for an unvisited cell adjacent to the "
        "currently carved maze. Creates mazes with long corridors and noticeable dead ends.",
    Algorithm.KRUSKALS:
        "Kruskal's algorithm treats the grid as a graph, randomly merging cells by removing "
        "walls to form a minimum spanning tree. It creates mazes with a uniform, tree-like "
        "structure and no bias in direction.",
    Algorithm.PRIMS:
        "Prim's algorithm starts with a random cell and grows the maze by adding passages to "
        "unvisited neighbors with the lowest random weights. It produces mazes with a uniform "
        "structure and moderate-length passages.",
    Algorithm.RECURSIVE_BACKTRACKER:
        "Essentially a depth-first search, this algorithm recursively explores neighbors and "
        "backtracks upon reaching dead ends. It's fast and generates mazes with long, twisting "
        "passages and fewer short loops.",
    Algorithm.RECURSIVE_DIVISION:
        "This method starts with an open grid and recursively divides it into chambers by "
        "adding walls with random passages. It creates mazes with a hierarchical layout, "
        "featuring long walls and fewer dead ends.",
    Algorithm.REVERSE_DELETE:
        "Beginning with a fully open grid, this algorithm randomly adds walls between adjacent "
        "cells, but only if the addition doesn't isolate any part of the maze. This creates a "
        "perfect maze with balanced passages and no directional bias.",
    Algorithm.SIDEWINDER:
        "Processed row-by-row, this algorithm carves eastward passages with occasional upward "
        "connections. It creates mazes with a strong horizontal bias and randomly placed "
        "vertical links.",
    Algorithm.WILSONS:
        "Wilson's algorithm uses loop-erased random walks, starting from a random cell and "
        "extending a path until it connects with the growing maze. It produces uniformly random "
        "mazes and avoids the inefficiencies of Aldous-Broder.",
}

# ---------------------------------------------------------------------------
# Per-type algorithm exclusion sets  (mirrors MazeAlgorithm.availableAlgorithms)
# ---------------------------------------------------------------------------

_NON_ORTHO_EXCLUDED: frozenset[Algorithm] = frozenset({
    Algorithm.BINARY_TREE,
    Algorithm.SIDEWINDER,
    Algorithm.ELLERS,
    Algorithm.RECURSIVE_DIVISION,
})

_ALGO_EXCLUSIONS: dict[MazeType, frozenset[Algorithm]] = {
    MazeType.ORTHOGONAL: frozenset(),
    MazeType.RHOMBIC:    frozenset({
        Algorithm.BINARY_TREE, Algorithm.SIDEWINDER, Algorithm.ELLERS,
        Algorithm.GROWING_TREE_NEWEST, Algorithm.GROWING_TREE_RANDOM,
        Algorithm.HUNT_AND_KILL,
    }),
    MazeType.DELTA:   _NON_ORTHO_EXCLUDED,
    MazeType.SIGMA:   _NON_ORTHO_EXCLUDED,
    MazeType.UPSILON: _NON_ORTHO_EXCLUDED,
}

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_MENU_W      = 520
_ROW_H       = 38
_PAD         = 20
_LABEL_W     = 110
_ARROW_W     = 28
_BTN_H       = 42
_TITLE_H     = 32
_ERROR_H     = 22
_DESC_H_TYPE = 48    # ~2 wrapped lines for short type descriptions
_DESC_H_ALGO = 76    # ~3 wrapped lines for longer algorithm descriptions
_DESC_GAP    = 4

_MENU_H = (
    _PAD + _TITLE_H + _PAD
    + _ROW_H + _DESC_GAP + _DESC_H_TYPE + _PAD // 2   # Grid Type + desc
    + _ROW_H + _DESC_GAP + _DESC_H_ALGO + _PAD // 2   # Algorithm + desc
    + _ROW_H + _ROW_H                                  # Width + Height
    + _PAD + _BTN_H + _PAD // 2 + _ERROR_H + _PAD
)


# ---------------------------------------------------------------------------
# MenuLayout — clickable regions produced by draw_menu
# ---------------------------------------------------------------------------


@dataclass
class MenuLayout:
    """Pixel rects produced by a ``draw_menu`` call, used by ``handle_click``."""

    rows: dict[int, pygame.Rect]
    left_arrows: dict[int, pygame.Rect]
    right_arrows: dict[int, pygame.Rect]
    generate_btn: pygame.Rect
    panel: pygame.Rect  # bounding rect of the whole panel; clicks outside cancel


# ---------------------------------------------------------------------------
# MenuState — pure data + event logic
# ---------------------------------------------------------------------------


class MenuState:
    """State for the in-game settings menu."""

    SUPPORTED_TYPES: list[MazeType] = [MazeType.ORTHOGONAL, MazeType.SIGMA, MazeType.DELTA, MazeType.RHOMBIC, MazeType.UPSILON]
    ALGORITHMS: list[Algorithm] = list(Algorithm)

    SECTION_TYPE = 0
    SECTION_ALGO = 1
    SECTION_WIDTH = 2
    SECTION_HEIGHT = 3
    SECTION_GENERATE = 4
    NUM_SECTIONS = 5

    MIN_SIZE = 2
    MAX_SIZE = 40

    def __init__(
        self,
        request: MazeRequest,
        max_sizes: dict | None = None,
        animate_mode: bool = False,
        anim_max_w: int = 30,
        anim_max_h: int = 20,
    ) -> None:
        self.type_idx: int = self.SUPPORTED_TYPES.index(request.maze_type)
        self.section: int = self.SECTION_TYPE
        self.error: str | None = None
        self.btn_pressed: bool = False  # True while Space or mouse button is held on Generate
        self._max_sizes = max_sizes
        self._animate_mode = animate_mode
        self._anim_max_w = anim_max_w
        self._anim_max_h = anim_max_h
        # algo_idx indexes into _compatible_algos for the current type.
        compatible = self._compatible_algos
        self.algo_idx: int = compatible.index(request.algorithm) if request.algorithm in compatible else 0
        self.width: int = request.width
        self.height: int = request.height
        # Clamp width/height to the effective max on open.
        max_w, max_h = self._effective_max()
        self.width = max(self.MIN_SIZE, min(self.width, max_w))
        self.height = max(self.MIN_SIZE, min(self.height, max_h))

    # -- Filtered algorithm list for current type ----------------------------

    @property
    def _compatible_algos(self) -> list[Algorithm]:
        """Algorithms valid for the currently-selected maze type."""
        excluded = _ALGO_EXCLUSIONS.get(self.SUPPORTED_TYPES[self.type_idx], frozenset())
        return [a for a in self.ALGORITHMS if a not in excluded]

    # -- Keyboard ------------------------------------------------------------

    def handle_keydown(self, key: int) -> tuple[bool, MazeRequest | None]:
        """Handle a KEYDOWN event. Returns ``(menu_open, request_or_None)``."""
        if key in (pygame.K_ESCAPE, pygame.K_m):
            self.btn_pressed = False
            return False, None
        if key == pygame.K_UP:
            self.section = (self.section - 1) % self.NUM_SECTIONS
            self.error = None
            return True, None
        if key == pygame.K_DOWN:
            self.section = (self.section + 1) % self.NUM_SECTIONS
            self.error = None
            return True, None
        if key == pygame.K_LEFT:
            self._change_value(-1)
            return True, None
        if key == pygame.K_RIGHT:
            self._change_value(1)
            return True, None
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and not self.btn_pressed:
            # Show the Generate button as pressed; fire on KEYUP so the visual
            # feedback is visible before the menu closes.
            self.btn_pressed = True
            self.section = self.SECTION_GENERATE
            return True, None
        return True, None

    def handle_keyup(self, key: int) -> tuple[bool, MazeRequest | None]:
        """Handle a KEYUP event. Space and Enter fire Generate on release.

        KEYDOWN only showed the pressed state; the actual generate happens here
        so the button color change is visible before the menu closes.
        """
        if key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER) and self.btn_pressed:
            self.btn_pressed = False
            return self._do_generate()
        return True, None

    # -- Mouse ---------------------------------------------------------------

    def handle_mousedown(
        self, pos: tuple[int, int], layout: MenuLayout
    ) -> tuple[bool, MazeRequest | None]:
        """Handle MOUSEBUTTONDOWN. For the Generate button, shows pressed state
        without firing yet — the generate fires on MOUSEBUTTONUP (``handle_mouseup``).
        All other regions (arrows, row selection, outside-panel cancel) fire immediately.
        """
        if not layout.panel.collidepoint(pos):
            return False, None
        for section, rect in layout.left_arrows.items():
            if rect.collidepoint(pos):
                self.section = section
                self._change_value(-1)
                return True, None
        for section, rect in layout.right_arrows.items():
            if rect.collidepoint(pos):
                self.section = section
                self._change_value(1)
                return True, None
        if layout.generate_btn.collidepoint(pos):
            self.section = self.SECTION_GENERATE
            self.btn_pressed = True
            return True, None
        for section, rect in layout.rows.items():
            if rect.collidepoint(pos):
                self.section = section
                return True, None
        return True, None

    def handle_mouseup(
        self, pos: tuple[int, int], layout: MenuLayout
    ) -> tuple[bool, MazeRequest | None]:
        """Handle MOUSEBUTTONUP. Fires Generate if the button was held down and
        the cursor is still over the button; always clears ``btn_pressed``."""
        was_pressed = self.btn_pressed
        self.btn_pressed = False
        if was_pressed and layout.generate_btn.collidepoint(pos):
            return self._do_generate()
        return True, None

    def handle_click(
        self, pos: tuple[int, int], layout: MenuLayout
    ) -> tuple[bool, MazeRequest | None]:
        """Handle a left-click (fires on MOUSEDOWN — kept for backward compat).

        Prefer ``handle_mousedown`` + ``handle_mouseup`` for the full press
        visual; this method is retained so existing call-sites and tests keep
        working without change.
        """
        if not layout.panel.collidepoint(pos):
            return False, None
        for section, rect in layout.left_arrows.items():
            if rect.collidepoint(pos):
                self.section = section
                self._change_value(-1)
                return True, None
        for section, rect in layout.right_arrows.items():
            if rect.collidepoint(pos):
                self.section = section
                self._change_value(1)
                return True, None
        if layout.generate_btn.collidepoint(pos):
            self.section = self.SECTION_GENERATE
            return self._do_generate()
        for section, rect in layout.rows.items():
            if rect.collidepoint(pos):
                self.section = section
                return True, None
        return True, None

    # -- Error feedback from caller ------------------------------------------

    def set_generation_error(self) -> None:
        """Called by app.py when the Rust rejects the chosen combination."""
        algo = self._compatible_algos[self.algo_idx]
        maze_type = self.SUPPORTED_TYPES[self.type_idx]
        self.error = f"{_ALGO_DISPLAY_NAME.get(algo, algo.value)} isn't compatible with {maze_type.value} — pick another."
        self.section = self.SECTION_ALGO

    # -- Helpers -------------------------------------------------------------

    def _effective_max(self) -> tuple[int, int]:
        """Return (max_width, max_height) for the currently selected maze type.

        Combines the screen-based limit (from *max_sizes*) with the per-side
        animation cap (when *animate_mode* is True).
        """
        mt = self.SUPPORTED_TYPES[self.type_idx]
        if self._max_sizes is not None:
            screen_max = self._max_sizes.get(mt, (self.MAX_SIZE, self.MAX_SIZE))
        else:
            screen_max = (self.MAX_SIZE, self.MAX_SIZE)
        if self._animate_mode:
            return (
                min(screen_max[0], self._anim_max_w),
                min(screen_max[1], self._anim_max_h),
            )
        return screen_max

    def _change_value(self, delta: int) -> None:
        self.error = None
        if self.section == self.SECTION_TYPE:
            # Snapshot current algorithm before the type changes.
            current_algo = self._compatible_algos[self.algo_idx]
            self.type_idx = (self.type_idx + delta) % len(self.SUPPORTED_TYPES)
            # Re-seat algo_idx in the new compatible list; fall back to 0 if incompatible.
            new_compat = self._compatible_algos
            self.algo_idx = new_compat.index(current_algo) if current_algo in new_compat else 0
            # Re-clamp width/height for the new type's screen limits.
            max_w, max_h = self._effective_max()
            self.width = min(self.width, max_w)
            self.height = min(self.height, max_h)
        elif self.section == self.SECTION_ALGO:
            self.algo_idx = (self.algo_idx + delta) % len(self._compatible_algos)
        elif self.section == self.SECTION_WIDTH:
            max_w, _ = self._effective_max()
            self.width = max(self.MIN_SIZE, min(max_w, self.width + delta))
        elif self.section == self.SECTION_HEIGHT:
            _, max_h = self._effective_max()
            self.height = max(self.MIN_SIZE, min(max_h, self.height + delta))

    def _do_generate(self) -> tuple[bool, MazeRequest | None]:
        """Build and return a MazeRequest unconditionally (section check bypassed)."""
        maze_type = self.SUPPORTED_TYPES[self.type_idx]
        algorithm = self._compatible_algos[self.algo_idx]
        # Rhombic only has (x+y)%2==0 cells; nudge the goal by one when the
        # menu dimensions place it on a non-existent odd-sum coord.  Mirrors
        # the same guard applied by app._build_request for CLI args.
        goal_x, goal_y = self.width - 1, self.height - 1
        if maze_type == MazeType.RHOMBIC and (goal_x + goal_y) % 2 != 0:
            goal_x = max(0, goal_x - 1)
        return False, MazeRequest(
            maze_type=maze_type,
            width=self.width,
            height=self.height,
            algorithm=algorithm,
            capture_steps=False,
            start=Coord(x=0, y=0),
            goal=Coord(x=goal_x, y=goal_y),
        )

    def _build_request(self) -> tuple[bool, MazeRequest | None]:
        if self.section != self.SECTION_GENERATE:
            return True, None
        return self._do_generate()


# ---------------------------------------------------------------------------
# Renderer helpers
# ---------------------------------------------------------------------------


def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Break *text* into lines that each fit within *max_width* pixels (greedy)."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        if font.size(test)[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_nav_row(
    surface: pygame.Surface,
    font: pygame.font.Font,
    layout: MenuLayout,
    state: MenuState,
    cy: int,
    section: int,
    label: str,
    value: str,
    px: int,
) -> None:
    """Draw one navigation row: focused highlight, label, ‹ value ›, arrows."""
    row_rect = pygame.Rect(px + 4, cy, _MENU_W - 8, _ROW_H - 4)
    layout.rows[section] = row_rect

    if state.section == section:
        pygame.draw.rect(surface, _FOCUSED_BG, row_rect, border_radius=6)

    # Label.
    lbl = font.render(label + ":", True, _LABEL_COLOR)
    surface.blit(lbl, (px + _PAD, cy + (_ROW_H - lbl.get_height()) // 2))

    ac = _ARROW_ACTIVE if state.section == section else _ARROW_IDLE
    val_area_x = px + _PAD + _LABEL_W
    right_arrow_x = px + _MENU_W - _PAD - _ARROW_W

    # ‹ left arrow.
    la = pygame.Rect(val_area_x, cy + 6, _ARROW_W, _ROW_H - 12)
    layout.left_arrows[section] = la
    pygame.draw.polygon(surface, ac, [
        (la.right - 6, la.top + 4),
        (la.left + 4, la.centery),
        (la.right - 6, la.bottom - 4),
    ])

    # Value text (centred between arrows).
    inner_cx = (val_area_x + _ARROW_W + right_arrow_x) // 2
    val_surf = font.render(value, True, _VALUE_COLOR)
    surface.blit(val_surf, val_surf.get_rect(centerx=inner_cx, centery=cy + _ROW_H // 2))

    # › right arrow.
    ra = pygame.Rect(right_arrow_x, cy + 6, _ARROW_W, _ROW_H - 12)
    layout.right_arrows[section] = ra
    pygame.draw.polygon(surface, ac, [
        (ra.left + 6, ra.top + 4),
        (ra.right - 4, ra.centery),
        (ra.left + 6, ra.bottom - 4),
    ])


def _draw_desc_area(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    rect: pygame.Rect,
    focused: bool,
) -> None:
    """Draw wrapped description text inside *rect*."""
    color = _DESC_BRIGHT if focused else _DESC_DIM
    lines = _wrap_text(text, font, rect.width)
    y = rect.top
    line_h = font.get_linesize()
    for line in lines:
        if y + line_h > rect.bottom:
            break
        surf = font.render(line, True, color)
        surface.blit(surf, (rect.left, y))
        y += line_h


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def draw_menu(
    surface: pygame.Surface,
    state: MenuState,
    font: pygame.font.Font,
) -> MenuLayout:
    """Draw the menu modal onto *surface*. Returns a ``MenuLayout`` for click handling."""
    layout = MenuLayout(rows={}, left_arrows={}, right_arrows={}, generate_btn=pygame.Rect(0, 0, 0, 0), panel=pygame.Rect(0, 0, 0, 0))

    # Dim the background.
    dim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    dim.fill(_OVERLAY_RGBA)
    surface.blit(dim, (0, 0))

    sw, sh = surface.get_size()
    px = (sw - _MENU_W) // 2
    py = (sh - _MENU_H) // 2

    # Panel background.
    panel = pygame.Rect(px, py, _MENU_W, _MENU_H)
    layout.panel = panel
    pygame.draw.rect(surface, _PANEL_BG, panel, border_radius=12)
    pygame.draw.rect(surface, _PANEL_BORDER, panel, width=2, border_radius=12)

    # Title.
    title = font.render("Maze Settings", True, _TITLE_COLOR)
    surface.blit(title, (px + _PAD, py + _PAD + (_TITLE_H - title.get_height()) // 2))

    cy = py + _PAD + _TITLE_H + _PAD

    # -- Grid Type row + description ----------------------------------------
    cur_type = state.SUPPORTED_TYPES[state.type_idx]
    _draw_nav_row(surface, font, layout, state, cy, MenuState.SECTION_TYPE,
                  "Grid Type", cur_type.value, px)
    cy += _ROW_H
    desc_rect = pygame.Rect(px + _PAD, cy + _DESC_GAP, _MENU_W - 2 * _PAD, _DESC_H_TYPE)
    _draw_desc_area(surface, font, _TYPE_DESC.get(cur_type, ""), desc_rect,
                    focused=(state.section == MenuState.SECTION_TYPE))
    cy += _DESC_GAP + _DESC_H_TYPE + _PAD // 2

    # -- Algorithm row + description ----------------------------------------
    compat = state._compatible_algos
    cur_algo = compat[state.algo_idx]
    algo_label = _ALGO_DISPLAY_NAME.get(cur_algo, cur_algo.value)
    _draw_nav_row(surface, font, layout, state, cy, MenuState.SECTION_ALGO,
                  "Algorithm", algo_label, px)
    cy += _ROW_H
    desc_rect = pygame.Rect(px + _PAD, cy + _DESC_GAP, _MENU_W - 2 * _PAD, _DESC_H_ALGO)
    _draw_desc_area(surface, font, _ALGO_DESC.get(cur_algo, ""), desc_rect,
                    focused=(state.section == MenuState.SECTION_ALGO))
    cy += _DESC_GAP + _DESC_H_ALGO + _PAD // 2

    # -- Width row ----------------------------------------------------------
    _draw_nav_row(surface, font, layout, state, cy, MenuState.SECTION_WIDTH,
                  "Width", str(state.width), px)
    cy += _ROW_H

    # -- Height row ---------------------------------------------------------
    _draw_nav_row(surface, font, layout, state, cy, MenuState.SECTION_HEIGHT,
                  "Height", str(state.height), px)
    cy += _ROW_H

    # -- Generate button ----------------------------------------------------
    cy += _PAD
    btn_w = 160
    btn_rect = pygame.Rect(px + (_MENU_W - btn_w) // 2, cy, btn_w, _BTN_H)
    layout.generate_btn = btn_rect
    layout.rows[MenuState.SECTION_GENERATE] = btn_rect
    if state.btn_pressed:
        btn_color = _BTN_PRESSED
        txt_color = _BTN_PRESSED_TEXT
    elif state.section == MenuState.SECTION_GENERATE:
        btn_color = _BTN_FOCUSED
        txt_color = _BTN_TEXT
    else:
        btn_color = _BTN_COLOR
        txt_color = _BTN_TEXT
    pygame.draw.rect(surface, btn_color, btn_rect, border_radius=8)
    btn_text = font.render("Generate", True, txt_color)
    surface.blit(btn_text, btn_text.get_rect(center=btn_rect.center))

    # -- Error message / animation-mode info note ---------------------------
    cy += _BTN_H + _PAD // 2
    if state.error:
        err = font.render(state.error, True, _ERROR_COLOR)
        surface.blit(err, err.get_rect(centerx=px + _MENU_W // 2, top=cy))
    elif state._animate_mode:
        note = font.render(
            f"Anim mode active — max {state._anim_max_w}×{state._anim_max_h}",
            True,
            _ANIM_NOTE_COLOR,
        )
        surface.blit(note, note.get_rect(centerx=px + _MENU_W // 2, top=cy))

    return layout
