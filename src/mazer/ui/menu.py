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
# Palette
# ---------------------------------------------------------------------------

_OVERLAY_RGBA = (0, 0, 0, 160)
_PANEL_BG = (245, 245, 250)
_PANEL_BORDER = (190, 200, 220)
_FOCUSED_BG = (210, 225, 255)
_TITLE_COLOR = (30, 30, 50)
_LABEL_COLOR = (60, 60, 80)
_VALUE_COLOR = (30, 30, 30)
_ARROW_IDLE = (160, 160, 200)
_ARROW_ACTIVE = (80, 100, 200)
_BTN_COLOR = (60, 120, 220)
_BTN_FOCUSED = (40, 90, 190)
_BTN_PRESSED = (20, 55, 140)       # darker still — held-down / space-held visual
_BTN_TEXT = (255, 255, 255)
_BTN_PRESSED_TEXT = (200, 220, 255)  # slightly dimmed white for pressed state
_ERROR_COLOR = (200, 30, 30)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_MENU_W = 460
_ROW_H = 38
_PAD = 20
_LABEL_W = 110
_ARROW_W = 28
_BTN_H = 42
_TITLE_H = 32
_ERROR_H = 22
_MENU_H = (
    _PAD
    + _TITLE_H
    + _PAD
    + 4 * _ROW_H  # type, algo, width, height
    + _PAD
    + _BTN_H
    + _PAD // 2
    + _ERROR_H
    + _PAD
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

    def __init__(self, request: MazeRequest) -> None:
        self.type_idx: int = self.SUPPORTED_TYPES.index(request.maze_type)
        self.algo_idx: int = self.ALGORITHMS.index(request.algorithm)
        self.width: int = request.width
        self.height: int = request.height
        self.section: int = self.SECTION_TYPE
        self.error: str | None = None
        self.btn_pressed: bool = False  # True while Space or mouse button is held on Generate

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
        algo = self.ALGORITHMS[self.algo_idx]
        maze_type = self.SUPPORTED_TYPES[self.type_idx]
        self.error = f"{algo.value} isn't compatible with {maze_type.value} — pick another."
        self.section = self.SECTION_ALGO

    # -- Helpers -------------------------------------------------------------

    def _change_value(self, delta: int) -> None:
        self.error = None
        if self.section == self.SECTION_TYPE:
            self.type_idx = (self.type_idx + delta) % len(self.SUPPORTED_TYPES)
        elif self.section == self.SECTION_ALGO:
            self.algo_idx = (self.algo_idx + delta) % len(self.ALGORITHMS)
        elif self.section == self.SECTION_WIDTH:
            self.width = max(self.MIN_SIZE, min(self.MAX_SIZE, self.width + delta))
        elif self.section == self.SECTION_HEIGHT:
            self.height = max(self.MIN_SIZE, min(self.MAX_SIZE, self.height + delta))

    def _do_generate(self) -> tuple[bool, MazeRequest | None]:
        """Build and return a MazeRequest unconditionally (section check bypassed)."""
        maze_type = self.SUPPORTED_TYPES[self.type_idx]
        algorithm = self.ALGORITHMS[self.algo_idx]
        return False, MazeRequest(
            maze_type=maze_type,
            width=self.width,
            height=self.height,
            algorithm=algorithm,
            capture_steps=False,
            start=Coord(x=0, y=0),
            goal=Coord(x=self.width - 1, y=self.height - 1),
        )

    def _build_request(self) -> tuple[bool, MazeRequest | None]:
        if self.section != self.SECTION_GENERATE:
            return True, None
        return self._do_generate()


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

    # Data rows.
    _row_specs = [
        (MenuState.SECTION_TYPE,   "Maze Type",  MenuState.SUPPORTED_TYPES[state.type_idx].value),
        (MenuState.SECTION_ALGO,   "Algorithm",  MenuState.ALGORITHMS[state.algo_idx].value),
        (MenuState.SECTION_WIDTH,  "Width",      str(state.width)),
        (MenuState.SECTION_HEIGHT, "Height",     str(state.height)),
    ]

    val_area_x = px + _PAD + _LABEL_W          # left edge of value column
    val_area_w = _MENU_W - _PAD - _LABEL_W - _PAD  # total width of value column
    right_arrow_x = px + _MENU_W - _PAD - _ARROW_W  # fixed right edge

    for section, label, value in _row_specs:
        row_rect = pygame.Rect(px + 4, cy, _MENU_W - 8, _ROW_H - 4)
        layout.rows[section] = row_rect

        if state.section == section:
            pygame.draw.rect(surface, _FOCUSED_BG, row_rect, border_radius=6)

        # Label.
        lbl = font.render(label + ":", True, _LABEL_COLOR)
        surface.blit(lbl, (px + _PAD, cy + (_ROW_H - lbl.get_height()) // 2))

        # Arrow colour depends on focus.
        ac = _ARROW_ACTIVE if state.section == section else _ARROW_IDLE

        # ‹ left arrow.
        la = pygame.Rect(val_area_x, cy + 6, _ARROW_W, _ROW_H - 12)
        layout.left_arrows[section] = la
        pygame.draw.polygon(surface, ac, [
            (la.right - 6, la.top + 4),
            (la.left + 4, la.centery),
            (la.right - 6, la.bottom - 4),
        ])

        # Value text (centred in the space between arrows).
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

        cy += _ROW_H

    # Generate button.
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

    # Error message.
    if state.error:
        cy += _BTN_H + _PAD // 2
        err = font.render(state.error, True, _ERROR_COLOR)
        surface.blit(err, err.get_rect(centerx=px + _MENU_W // 2, top=cy))

    return layout
