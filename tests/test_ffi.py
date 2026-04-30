"""FFI-layer safety-net tests.

These tests poke the raw cffi bindings: pointers, manual allocation, manual
free. Every other test in the project sits *on top of* the wrapper in
``mazer.maze``; this file is what catches breakage at the C boundary —
struct layout drift, missing symbols, ABI mismatch, double-free, leaks.

It's intentionally ugly. Real Python code shouldn't look like this; the
``Maze`` wrapper exists precisely so callers don't have to. But the cost of
finding an FFI bug at the wrapper level (a confusing AttributeError or a
silent memory corruption) is much higher than finding it here.

Each test that allocates a Grid wraps the work in try/finally so cleanup
runs even on assertion failure — pytest reruns and parametrize can hide
leaks otherwise. We never use a fixture for the Grid: doing so would
couple cleanup to fixture teardown semantics, which has different ordering
guarantees than try/finally and obscures what's being tested.
"""

from __future__ import annotations

import json

import pytest

from mazer._ffi import ffi, lib


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _cstr(s: str):
    """Encode a Python str into a cffi-owned NUL-terminated C string.

    The returned object owns the memory and is freed when it goes out of
    scope on the Python side; callers should hold the reference for as
    long as the C side reads from it.
    """
    return ffi.new("char[]", s.encode("utf-8"))


def _request_json(**overrides) -> str:
    """Build a maze-generation JSON request with sane defaults.

    Defaults produce a small Orthogonal maze that all algorithms support,
    so individual tests only have to override the fields they care about.
    """
    request = {
        "maze_type": "Orthogonal",
        "width": 5,
        "height": 5,
        "algorithm": "RecursiveBacktracker",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 4, "y": 4},
    }
    request.update(overrides)
    return json.dumps(request)


def _generate(request_str: str):
    """Generate a Grid from a JSON request; assert non-null and return the pointer."""
    grid = lib.mazer_generate_maze(_cstr(request_str))
    assert grid != ffi.NULL, "mazer_generate_maze returned NULL for request: " + request_str
    return grid


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
def test_ffi_integration_returns_42():
    """Smoke test: the canary symbol is reachable and ABI is sane.

    If this fails, the .so didn't load, the symbol isn't exported, or
    int return-value marshalling is broken — anything more elaborate is
    a waste of time until this passes.
    """
    assert lib.mazer_ffi_integration_test() == 42


def test_generate_and_destroy_orthogonal():
    """Round-trip a Grid through the C heap: generate, then destroy.

    No assertion beyond "non-null pointer" — the value lives in Rust and
    isn't introspectable from here. The real test is that mazer_destroy
    doesn't crash; if it segfaults or trips an allocator-debugging hook
    (e.g. MallocStackLogging), the process dies and the test fails.
    """
    grid = _generate(_request_json())
    lib.mazer_destroy(grid)


def test_get_cells_length_matches_dimensions():
    """For an Orthogonal NxM maze, mazer_get_cells should return N*M cells.

    Also verifies the out-pointer protocol: we pass `length` as a
    `size_t *` and read the count back from `length[0]` after the call.
    """
    width, height = 5, 7
    grid = _generate(_request_json(width=width, height=height,
                                   goal={"x": width - 1, "y": height - 1}))
    try:
        length = ffi.new("size_t *")
        cells = lib.mazer_get_cells(grid, length)
        try:
            assert cells != ffi.NULL
            assert length[0] == width * height, (
                f"expected {width}*{height}={width*height} cells, got {length[0]}"
            )
        finally:
            # mazer_free_cells must be matched 1:1 with mazer_get_cells.
            # Skipping it leaks the FFICell array AND the per-cell C strings
            # owned by each FFICell's Drop impl on the Rust side.
            lib.mazer_free_cells(cells, length[0])
    finally:
        lib.mazer_destroy(grid)


def test_invalid_direction_returns_null():
    """mazer_make_move must reject unknown direction strings with NULL.

    The Rust side parses the direction string via Direction::try_from, which
    fails for anything that isn't an exact enum variant name. NULL is the
    documented signal for "move did not happen" — used both for blocked
    moves (e.g. into a wall) and for malformed input. The Python wrapper
    in Stage 3 will translate this into a `False` return from `Maze.move`.
    """
    grid = _generate(_request_json(width=3, height=3,
                                   goal={"x": 2, "y": 2}))
    try:
        result = lib.mazer_make_move(grid, _cstr("NotADirection"))
        assert result == ffi.NULL
    finally:
        lib.mazer_destroy(grid)


def test_capture_steps_records_and_yields_step_cells():
    """With `capture_steps: true`, intermediate generation snapshots are stored.

    The count is implementation-defined (depends on algorithm) but must be
    > 0 for any non-trivial maze. We fetch step 0 — guaranteed to exist if
    count > 0 — and verify the same allocation/free protocol as the
    full-maze cells. Without `capture_steps: true`, mazer_get_generation_steps_count
    returns 0 and mazer_get_generation_step_cells returns NULL; we trust
    the Rust unit tests on those negative paths and exercise only the
    happy path here.
    """
    grid = _generate(_request_json(width=4, height=4,
                                   algorithm="HuntAndKill",
                                   goal={"x": 3, "y": 3},
                                   capture_steps=True))
    try:
        steps_count = lib.mazer_get_generation_steps_count(grid)
        assert steps_count > 0, "expected capture_steps=True to record some steps"

        length = ffi.new("size_t *")
        cells = lib.mazer_get_generation_step_cells(grid, 0, length)
        try:
            assert cells != ffi.NULL
            assert length[0] > 0
        finally:
            lib.mazer_free_cells(cells, length[0])
    finally:
        lib.mazer_destroy(grid)
