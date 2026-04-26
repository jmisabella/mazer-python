"""High-level Pythonic wrapper over the cffi binding.

``Maze`` is the only object callers should ever hold: it owns the C ``Grid``
pointer, manages its lifetime via the context-manager protocol, and hands
out plain-Python ``Cell`` snapshots so no FFI types leak into game logic
or the renderer.

Why ``Cell`` is a frozen dataclass copied out of ``FFICell``:
    The FFI's ``FFICell`` array is owned by Rust and only valid until
    ``mazer_free_cells`` runs. If we handed those structs back to Python
    code, any caller that hung onto one past the free would dereference
    freed memory. Copying into immutable Python objects severs that
    lifetime entirely — the cffi memory is freed inside ``cells()`` before
    the function returns.

Why ``cells()`` caches:
    A single ``cells()`` call decodes ~5 cffi values per cell into Python
    objects and constructs a frozenset. For UI redraws at 60fps that adds
    up. The cache is invalidated on ``move()`` because that's the only
    operation that mutates the grid; generation_steps is read-only.

Why ``move()`` returns a bool instead of raising:
    Walking into a wall is normal gameplay, not an error. Reserving the
    exception channel for "this maze is unusable" (closed, NULL grid)
    keeps the call site clean: ``if maze.move(d): ...``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from mazer._ffi import ffi, lib
from mazer.types import Coord, Direction, MazeRequest, MazeType


class MazeGenerationError(Exception):
    """Raised when ``mazer_generate_maze`` returns NULL.

    The Rust side logs the specific reason to stderr (invalid JSON,
    incompatible algorithm/maze_type combination, zero-size grid, etc.);
    we don't have access to that across the FFI, so the message just
    echoes the request.
    """


@dataclass(frozen=True)
class Cell:
    """Immutable, FFI-free snapshot of a single maze cell.

    Field order and names mirror ``FFICell`` so the conversion in
    ``_cell_from_ffi`` is a straight transcription. ``linked`` is a
    ``frozenset`` (not a list) because membership tests dominate over
    iteration in renderer / pathfinding code, and frozenset hashes
    cleanly for the dataclass.
    """

    coord: Coord
    linked: frozenset[Direction]
    distance: int
    is_start: bool
    is_goal: bool
    is_active: bool
    is_visited: bool
    has_been_visited: bool
    on_solution_path: bool
    orientation: str
    is_square: bool
    maze_type: MazeType


def _cell_from_ffi(ffi_cell) -> Cell:
    """Copy one ``FFICell`` into a Python ``Cell``. No FFI handle escapes."""
    linked = frozenset(
        Direction(ffi.string(ffi_cell.linked[i]).decode("utf-8"))
        for i in range(ffi_cell.linked_len)
    )
    return Cell(
        coord=Coord(x=ffi_cell.x, y=ffi_cell.y),
        linked=linked,
        distance=ffi_cell.distance,
        is_start=bool(ffi_cell.is_start),
        is_goal=bool(ffi_cell.is_goal),
        is_active=bool(ffi_cell.is_active),
        is_visited=bool(ffi_cell.is_visited),
        has_been_visited=bool(ffi_cell.has_been_visited),
        on_solution_path=bool(ffi_cell.on_solution_path),
        orientation=ffi.string(ffi_cell.orientation).decode("utf-8"),
        is_square=bool(ffi_cell.is_square),
        maze_type=MazeType(ffi.string(ffi_cell.maze_type).decode("utf-8")),
    )


class Maze:
    """Owns one C ``Grid``. Use as a context manager for guaranteed cleanup.

    Lifetime invariants:
      * ``__init__`` either succeeds (grid pointer non-NULL) or raises
        ``MazeGenerationError``. There is no half-constructed state.
      * After ``close()`` (or ``__exit__``), the grid pointer is NULL and
        the instance is ``closed``. Any further call to ``cells``, ``move``,
        or ``generation_steps`` raises ``RuntimeError`` rather than feeding
        a NULL pointer to the FFI.
      * ``close()`` is idempotent — calling it multiple times is safe and
        only invokes ``mazer_destroy`` on the first call.
    """

    def __init__(self, request: MazeRequest) -> None:
        self._request = request
        # Build a NUL-terminated C string from the JSON. ``ffi.new("char[]", ...)``
        # allocates on the cffi side and the resulting cdata owns the memory
        # for the duration of this scope; mazer_generate_maze copies what it
        # needs out of the buffer before returning.
        c_request = ffi.new("char[]", request.to_json().encode("utf-8"))
        self._grid = lib.mazer_generate_maze(c_request)
        if self._grid == ffi.NULL:
            raise MazeGenerationError(
                f"mazer_generate_maze returned NULL for request: {request.to_json()}"
            )
        self._cells_cache: list[Cell] | None = None
        self._closed = False

    def __enter__(self) -> Maze:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def request(self) -> MazeRequest:
        """The original request that produced this maze (handy for ``R``-to-regenerate)."""
        return self._request

    def close(self) -> None:
        """Destroy the underlying C ``Grid``. Safe to call repeatedly."""
        if self._closed:
            return
        lib.mazer_destroy(self._grid)
        self._grid = ffi.NULL
        self._closed = True
        self._cells_cache = None

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError("operation on a closed Maze")

    def cells(self) -> list[Cell]:
        """Return the current cells. Cached until the next ``move()``."""
        self._check_open()
        if self._cells_cache is not None:
            return self._cells_cache
        length = ffi.new("size_t *")
        ffi_cells = lib.mazer_get_cells(self._grid, length)
        if ffi_cells == ffi.NULL:
            # mazer_get_cells only returns NULL on bad input; we just checked
            # _closed, so this would mean the FFI is in an unexpected state.
            raise RuntimeError("mazer_get_cells returned NULL")
        try:
            self._cells_cache = [_cell_from_ffi(ffi_cells[i]) for i in range(length[0])]
        finally:
            # Free the Rust-owned buffer immediately; our Python copies are
            # independent and don't reference the FFI memory anymore.
            lib.mazer_free_cells(ffi_cells, length[0])
        return self._cells_cache

    def move(self, direction: Direction) -> bool:
        """Attempt a move. Returns False for blocked or invalid moves.

        The Rust side returns NULL both for "wall in the way" and for
        unknown direction strings. From the Python caller's perspective
        both are "the move didn't happen"; conflating them matches how
        the game loop wants to handle it.
        """
        self._check_open()
        c_dir = ffi.new("char[]", direction.value.encode("utf-8"))
        result = lib.mazer_make_move(self._grid, c_dir)
        if result == ffi.NULL:
            return False
        # Successful move mutated the grid; drop the stale snapshot.
        self._cells_cache = None
        return True

    def generation_steps(self) -> Iterator[list[Cell]]:
        """Yield each captured generation step as its own Cell list.

        Empty iterator when the request didn't set ``capture_steps=True``.
        Lazy: each step's cffi buffer is fetched + freed independently so
        we don't hold all snapshots in C memory simultaneously.
        """
        self._check_open()
        count = lib.mazer_get_generation_steps_count(self._grid)
        for i in range(count):
            length = ffi.new("size_t *")
            ffi_cells = lib.mazer_get_generation_step_cells(self._grid, i, length)
            if ffi_cells == ffi.NULL:
                # Defensive: count said this index exists but the fetcher
                # disagrees. Skip rather than crash the iteration.
                continue
            try:
                step = [_cell_from_ffi(ffi_cells[j]) for j in range(length[0])]
            finally:
                lib.mazer_free_cells(ffi_cells, length[0])
            yield step


__all__ = ["Cell", "Maze", "MazeGenerationError"]
