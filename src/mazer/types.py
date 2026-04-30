"""Public, hand-typed Python equivalents of the Rust types the FFI accepts.

These enums and dataclasses are the input-side surface of the package: a
caller builds a ``MazeRequest``, hands it to ``Maze``, and never touches
cffi directly. The string values on the enums are the **on-the-wire**
strings the Rust side parses (e.g. ``"RecursiveBacktracker"``,
``"UpperLeft"``) — they're chosen to match the Rust enum debug format,
not Pythonic naming, because they're serialized into the JSON request
and into the per-cell ``linked`` direction names.

Why ``str, Enum`` rather than plain ``Enum``:
    Subclassing ``str`` means each member *is* its serialized form. We can
    feed ``Direction.UP`` straight to ``json.dumps`` and to ``Direction(...)``
    round-trips without conversion code.

Why MazeType lists all five variants even though Stage 4's UI is
Orthogonal-only:
    The wrapper is the full Pythonic API over the FFI. The Rust library
    accepts all five and Stage 3's tests only exercise Orthogonal, but
    omitting variants here would force a ``types.py`` edit later and risk
    the enum drifting from the FFI's accepted set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class MazeType(str, Enum):
    ORTHOGONAL = "Orthogonal"
    DELTA = "Delta"
    SIGMA = "Sigma"
    UPSILON = "Upsilon"
    RHOMBIC = "Rhombic"


class Algorithm(str, Enum):
    """All algorithms the Rust library accepts.

    Not every algorithm works for every maze type — e.g. the Rust side rejects
    ``BinaryTree`` on Delta. We don't enforce that here; the FFI returns NULL
    on an invalid combination and ``Maze`` raises ``MazeGenerationError``.
    Validation logic belongs at the UI/request-builder layer (Stage 4+),
    where it can give a useful message; baking it into the enum would
    couple ``types.py`` to maze-type compatibility tables that change with
    upstream Rust.
    """

    ALDOUS_BRODER = "AldousBroder"
    BINARY_TREE = "BinaryTree"
    ELLERS = "Ellers"
    GROWING_TREE_NEWEST = "GrowingTreeNewest"
    GROWING_TREE_RANDOM = "GrowingTreeRandom"
    HUNT_AND_KILL = "HuntAndKill"
    KRUSKALS = "Kruskals"
    PRIMS = "Prims"
    RECURSIVE_BACKTRACKER = "RecursiveBacktracker"
    RECURSIVE_DIVISION = "RecursiveDivision"
    REVERSE_DELETE = "ReverseDelete"
    SIDEWINDER = "Sidewinder"
    WILSONS = "Wilsons"


class Direction(str, Enum):
    """Move direction. Eight values to cover Orthogonal (4-way), Delta/Sigma
    (mixed), and Upsilon (8-way) cells with one enum.

    Values are the exact strings the Rust ``Direction::try_from`` accepts;
    sending anything else through ``mazer_make_move`` returns NULL.
    """

    UP = "Up"
    DOWN = "Down"
    LEFT = "Left"
    RIGHT = "Right"
    UPPER_LEFT = "UpperLeft"
    UPPER_RIGHT = "UpperRight"
    LOWER_LEFT = "LowerLeft"
    LOWER_RIGHT = "LowerRight"


@dataclass(frozen=True)
class Coord:
    """Grid coordinate. Frozen so it can live inside the frozen ``Cell``."""

    x: int
    y: int


@dataclass
class MazeRequest:
    """A maze-generation request. Serialized to JSON for the FFI.

    ``start`` and ``goal`` are optional — when omitted the Rust side picks
    sensible defaults (see the Rhombic test in ``ffi.rs`` for the no-coords
    form). When omitted from the request, they are also omitted from the
    JSON entirely (rather than serialized as ``null``) because the Rust
    deserializer expects the keys absent, not present-and-null.
    """

    maze_type: MazeType
    width: int
    height: int
    algorithm: Algorithm
    capture_steps: bool = False
    start: Coord | None = None
    goal: Coord | None = None

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "maze_type": self.maze_type.value,
            "width": self.width,
            "height": self.height,
            "algorithm": self.algorithm.value,
            "capture_steps": self.capture_steps,
        }
        if self.start is not None:
            payload["start"] = {"x": self.start.x, "y": self.start.y}
        if self.goal is not None:
            payload["goal"] = {"x": self.goal.x, "y": self.goal.y}
        return json.dumps(payload)


__all__ = [
    "Algorithm",
    "Coord",
    "Direction",
    "MazeRequest",
    "MazeType",
]
