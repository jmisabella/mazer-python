#!/usr/bin/env bash
# test.sh — pytest cheat sheet + the command this project actually runs.
#
# Personal study notes on Python unit testing with pytest.
# Prerequisite: venv active and dev deps installed. From the project root:
#   python3.13 -m venv .venv
#   source .venv/bin/activate
#   pip install -e '.[dev]'

set -euo pipefail


# ─── Virtual environment setup (one-time, from project root) ────────────────
# A virtual environment ("venv") is an isolated Python install — its own
# `python`, `pip`, and `site-packages/` — that prevents this project's deps
# from polluting (or being polluted by) your system Python. Always use one.
#
# IMPORTANT: every `pip` and `pytest` command below must be run with the venv
# ACTIVATED (your shell prompt should show a `(.venv)` prefix). Without
# activation, `pip install` writes to the system Python — and on modern macOS
# Apple blocks that with a PEP 668 "externally-managed-environment" error.
# The venv is your sandbox; activation is what tells your shell to use it.
#
# python3.13 -m venv .venv         # create .venv/ using Homebrew's Python 3.13
# source .venv/bin/activate        # activate: prompt gets a `(.venv)` prefix
# python --version                 # sanity check: should print 3.13.x
# pip install -e '.[dev]'          # install this project + dev extras (pytest)
# deactivate                       # leave the venv (when you're done for the day)
#
# After the first-time setup, future sessions only need `source .venv/bin/activate`.
#
# Anatomy of `pip install -e '.[dev]'`:
#   .            The "package" to install is the current directory — i.e., pip
#                reads pyproject.toml here and installs the `mazer` package it
#                declares.
#   -e           "Editable" install. Instead of copying files into
#                site-packages/, pip creates a link back to `src/mazer/`. Edits
#                to your source files take effect immediately — no reinstall
#                needed. Standard for local dev; never use in production.
#   [dev]        Install the optional dependency group named `dev`, declared
#                in pyproject.toml under [project.optional-dependencies]. For
#                this project that's just `pytest>=8`. You can have multiple
#                groups (e.g. [test], [docs]) and request them like '.[dev,docs]'.
#   '...'        The single quotes are mandatory in bash/zsh because `[dev]`
#                is a shell glob pattern. Unquoted, the shell tries to expand
#                it against filenames in the current directory and you'll get
#                "no matches found" or worse.
#
# To list what's installed in the venv: `pip list`
# To upgrade a package:                 `pip install -U <name>`
# To uninstall:                         `pip uninstall <name>`
# To freeze exact versions:             `pip freeze > requirements.txt`


# ─── Core invocation ────────────────────────────────────────────────────────
# pytest                # discover + run all tests under `testpaths` (see pyproject.toml)
# pytest -v             # verbose: print each test name and outcome
# pytest -q             # quiet: dots only, minimal output
# pytest -s             # don't capture stdout — `print()` calls become visible
# pytest -vs            # combine -v and -s
# pytest --tb=short     # shorter tracebacks on failure
# pytest --tb=line      # one-line tracebacks per failure
# pytest --tb=no        # no tracebacks (just pass/fail summary)


# ─── Selecting which tests to run ───────────────────────────────────────────
# pytest tests/test_maze.py                                  # one file
# pytest tests/test_maze.py::test_generate_small_maze        # one function
# pytest tests/test_maze.py::TestClass::test_method          # method on a class
# pytest -k "maze and not slow"                              # keyword expression on test names
# pytest -m integration                                      # by marker (see "Markers" below)


# ─── Failure / iteration flags (most useful in a TDD loop) ──────────────────
# pytest -x                # stop at first failure
# pytest --maxfail=3       # stop after 3 failures
# pytest --lf              # rerun only tests that failed last time ("last failed")
# pytest --ff              # run last-failed first, then everything else
# pytest --pdb             # drop into pdb on failure (post-mortem debugger)
# pytest -p no:cacheprovider   # disable .pytest_cache for one run


# ─── Collection / discovery ─────────────────────────────────────────────────
# pytest --collect-only    # list what would run without running anything
# pytest --co -q           # same, terse
# pytest --markers         # list all registered markers
# pytest --fixtures        # list all available fixtures (incl. ones from conftest)


# ─── Coverage (requires pytest-cov; not in this project's deps yet) ─────────
# pip install pytest-cov
# pytest --cov=mazer                              # coverage for the mazer package
# pytest --cov=mazer --cov-report=term-missing    # show uncovered line numbers in terminal
# pytest --cov=mazer --cov-report=html            # HTML report in htmlcov/


# ─── Concepts worth knowing (the interview-y stuff) ─────────────────────────
#
# 1. Test discovery
#    pytest finds files matching test_*.py or *_test.py, then functions named
#    test_*. Configurable via [tool.pytest.ini_options] in pyproject.toml.
#
# 2. Assertion introspection
#    pytest rewrites plain `assert` so that `assert x == y` prints both values
#    on failure. You never need self.assertEqual / assertTrue / etc.
#
# 3. Fixtures (the pytest replacement for setUp / tearDown)
#    A function decorated with @pytest.fixture. Tests "request" it by naming
#    it as a parameter. Anything before `yield` is setup; after `yield` is teardown.
#    Scope: function (default), class, module, session.
#
#      @pytest.fixture
#      def small_maze():
#          with Maze(MazeRequest(...)) as m:
#              yield m
#
#      def test_cells_count(small_maze):
#          assert len(small_maze.cells()) == 25
#
# 4. conftest.py
#    A special file pytest auto-discovers. Fixtures defined in conftest.py are
#    shared across every test file in that directory and below — no imports needed.
#    Use it to share setup across the suite.
#
# 5. Parametrize (data-driven tests)
#
#      @pytest.mark.parametrize("algorithm", [Algorithm.WILSONS, Algorithm.BINARY_TREE])
#      def test_algorithm_produces_solvable_maze(algorithm):
#          ...
#
#    pytest generates one test per parameter value; each appears separately in output.
#    Multi-arg form: @pytest.mark.parametrize("x,expected", [(1, 1), (2, 4), (3, 9)])
#
# 6. Markers (tags on tests)
#
#      @pytest.mark.slow                                       # custom marker
#      @pytest.mark.skip(reason="not yet implemented")
#      @pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
#      @pytest.mark.xfail(reason="known bug; expected to fail")
#
#    Custom markers should be registered in pyproject.toml:
#      [tool.pytest.ini_options]
#      markers = ["slow: marks tests that take >1s", "integration: hits the real FFI"]
#
# 7. Expected exceptions
#
#      with pytest.raises(MazeGenerationError, match="invalid"):
#          Maze(bad_request)
#
# 8. Capturing stdout/stderr
#
#      def test_prints_hello(capsys):
#          print("hello")
#          captured = capsys.readouterr()
#          assert captured.out == "hello\n"
#
# 9. Temp directories
#
#      def test_writes_file(tmp_path):
#          (tmp_path / "out.txt").write_text("hi")
#          ...
#
#    `tmp_path` is a built-in fixture — a fresh `pathlib.Path` per test, auto-cleaned.
#
# 10. Mocking
#     Built-in `monkeypatch` fixture for env vars, attrs, dict items.
#     For object/method mocking, use `unittest.mock.patch` or the `pytest-mock` plugin (`mocker` fixture).
#
# 11. unittest vs pytest
#     pytest can run unittest.TestCase classes unchanged. For new code, prefer
#     plain functions + fixtures — less boilerplate, better failure messages.
#
# 12. Hygiene rules of thumb
#     - Each test independent (no ordering dependency, no shared mutable state).
#     - Test names read like a sentence: test_<unit>_<scenario>_<expected>.
#     - Group related assertions; don't artificially limit to "one assert per test".
#     - Tests are documentation — name and structure them so they read as usage examples.
#
# 13. Exit codes (useful in CI)
#     0 = all passed, 1 = some failed, 2 = interrupted, 3 = internal error,
#     4 = pytest usage error, 5 = no tests collected.


# ─── Interview gotchas (the three things interviewers actually probe) ───────
#
# A. Fixture scopes — "when does setup re-run?"
#
#    Every @pytest.fixture has a scope that controls how often its setup runs:
#
#      scope="function"  (default)  — re-run for every test that requests it
#      scope="class"                 — once per test class
#      scope="module"                — once per .py file
#      scope="session"               — once for the entire pytest run
#
#    Example — expensive setup you only want to pay for ONCE:
#
#      @pytest.fixture(scope="session")
#      def ffi_lib():
#          # loading the native lib is slow; do it once for all tests
#          from mazer._ffi import lib
#          return lib
#
#    Common bug: a function-scoped fixture mutates state, but a higher-scoped
#    fixture caches a reference to that state — tests start interfering with
#    each other in non-obvious order-dependent ways. Rule of thumb: the wider
#    the scope, the more careful you must be that the fixture is read-only or
#    properly torn down via `yield` + cleanup.
#
#    `autouse=True` makes a fixture run for every test in scope without being
#    requested by name — handy, but easy to abuse. Prefer explicit requests.
#
#
# B. Why pytest beats unittest — two specific wins
#
#    1. Assertion introspection. With unittest you have to remember the right
#       method for each comparison (assertEqual, assertTrue, assertIn, assertIs,
#       assertRaises, assertAlmostEqual, ...). With pytest you write `assert`
#       and it shows you both sides on failure:
#
#         unittest:    self.assertEqual(maze.cells_count, 25)
#         pytest:      assert maze.cells_count == 25
#                                                  ^^ on failure, prints both values
#
#    2. Fixtures as function parameters, not inheritance. unittest forces you
#       into TestCase classes with setUp/tearDown shared by inheritance — which
#       gets messy when different tests need different setup. pytest fixtures
#       are à la carte: a test "requests" exactly the setup it needs by naming
#       fixtures as parameters. No class hierarchy required:
#
#         def test_solution_path(small_maze, captured_steps):  # request both
#             ...
#
#       Composition over inheritance, applied to test setup.
#
#
# C. Parametrize — one decorator, many tests
#
#    `@pytest.mark.parametrize` turns one test function into N tests, one per
#    parameter set. Each shows up SEPARATELY in the output (so a failure tells
#    you exactly which input broke), and you can see them via --collect-only.
#
#      @pytest.mark.parametrize("algorithm", [
#          Algorithm.WILSONS,
#          Algorithm.BINARY_TREE,
#          Algorithm.HUNT_AND_KILL,
#      ])
#      def test_algorithm_produces_solvable_maze(algorithm):
#          ...
#
#      # collected as 3 tests:
#      #   test_algorithm_produces_solvable_maze[Wilsons]
#      #   test_algorithm_produces_solvable_maze[BinaryTree]
#      #   test_algorithm_produces_solvable_maze[HuntAndKill]
#
#    Multi-arg form (great for input/expected pairs):
#
#      @pytest.mark.parametrize("size,expected_cells", [(3, 9), (5, 25), (10, 100)])
#      def test_orthogonal_cell_count(size, expected_cells):
#          ...
#
#    Why interviewers love it: it's the canonical test for the "DRY but readable"
#    instinct. Without it, people copy-paste the same test body for each input
#    (hard to maintain) or stuff a `for` loop inside one test (one failure stops
#    the loop and hides the rest).


# ─── The command this script actually runs ──────────────────────────────────
pytest -v
