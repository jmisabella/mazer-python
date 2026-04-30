Check for planned tasks in `.planning/` directory: `.planning/PLAN.md`.

The tasks will be explicitly planned across multiple Claude Code sessions in order to effectively manage context window ceiling. 

For each completed session task, mark the task as completed upon completion. Add any relevant notes that may be useful for documentation in each Stage session in `.planning/PLAN.md`.

There is referenced existing code:
- `.planning/referenced_resources/iOS_app/` has the entire iOS app that uses the compiled `mazer` library for reference. Note the `setup.sh` script at the root of `iOS_app/`
- `.planning/referenced_resources/rust_library/` has relevant files from the mazer Rust library:
  - `include/mazer.h` — the C FFI header (types and function signatures)
  - `src/ffi.rs` — Rust FFI entry points
  - `src/grid.rs` — core maze logic: `make_move` (with its per-direction forgiving fallback chain), neighbor assignment per maze type, sigma boundary clamping. **Check here first for "why does the game behave this way" questions.**



