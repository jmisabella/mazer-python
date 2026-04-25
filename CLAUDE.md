Check for planned tasks in `.planning/` directory: `.planning/PLAN.md`.

The tasks will be explicitly planned across multiple Claude Code sessions in order to effectively manage context window ceiling. 

For each completed session task, mark the task as completed upon completion. Add any relevant notes that may be useful for documentation in each Stage session in `.planning/PLAN.md`.

There is referenced existing code:
- `.planning/referenced_resources/iOS_app/` has the entire iOS app that uses the compiled `mazer` library for reference. Note the `setup.sh` script at the root of `iOS_app/`
- `.planning/referenced_resources/rust_library/` has relevant files from the mazer Rust library, specifically `include/mazer.h` header file and `src/ffi.rs`



