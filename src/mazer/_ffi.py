"""Runtime cffi binding for the native mazer library.

Re-exports ``ffi`` and ``lib`` from the compiled ``mazer._mazer_cffi``
extension. That extension is produced once at build time by
``mazer._ffi_build`` (run via ``./build.sh`` or directly with
``python -m mazer._ffi_build``); this module is the runtime entry point
the rest of the package imports.

Two layers, on purpose:

  * ``mazer._mazer_cffi``  — the compiled C extension (a ``.so`` file).
    Platform- and Python-version-specific; not in source control.
  * ``mazer._ffi``         — this file. Always present in the source tree.
    Pure Python that re-exports from the compiled extension and provides
    one human-readable place to land if the extension is missing.

If you see ``ImportError: mazer._mazer_cffi is not built`` you skipped a
build step — run ``./build.sh`` from the repo root.
"""

from __future__ import annotations

try:
    from mazer._mazer_cffi import ffi, lib  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - exercised when the build is missing
    raise ImportError(
        "mazer._mazer_cffi is not built. Run ./build.sh from the repo root, "
        "or `python -m mazer._ffi_build` after `./build_rust.sh`."
    ) from exc

__all__ = ["ffi", "lib"]
