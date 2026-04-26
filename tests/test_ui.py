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
