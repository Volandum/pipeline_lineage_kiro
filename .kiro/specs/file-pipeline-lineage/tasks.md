# Implementation Plan: file-pipeline-lineage

## Overview

Incremental build-up from project scaffolding through core data models, I/O interception, tracking, replay, and tests. Each task integrates with the previous so there is no orphaned code.

## Tasks

- [x] 1. Scaffold project structure
  - Create `pyproject.toml` with `[project]` metadata, `[build-system]` (hatchling), `[project.optional-dependencies]` for `dev` (pytest, hypothesis, ruff), and `[tool.pytest.ini_options]` pointing at `tests/`
  - Create `src/file_pipeline_lineage/__init__.py` with placeholder exports (all names, all raising `NotImplementedError` stubs acceptable at this stage)
  - Create `src/file_pipeline_lineage/exceptions.py` defining `LineageError`, `RunNotFoundError`, `MissingInputError`, `MissingCommitError`
  - Create empty `tests/` directory with `tests/conftest.py` (empty for now)
  - Create skeleton `INTERFACES.md` at project root with section headings only
  - _Requirements: 1.1, 2.1, 5.3_

- [x] 2. Implement `LineageRecord` dataclass and serialisation
  - [x] 2.1 Create `src/file_pipeline_lineage/record.py` with the frozen `LineageRecord` dataclass (all 10 fields per design)
    - Include `to_dict()` and `from_dict(cls, d)` classmethods for JSON round-trip; arrays serialise as lists, tuples deserialise back to `tuple[str, ...]`
    - _Requirements: 1.1, 2.1, 5.3_

  - [x] 2.2 Write property test for `LineageRecord` round-trip (Property 4 partial — serialisation only)
    - **Property 4: LineageStore save/load round-trip** (serialisation half)
    - **Validates: Requirements 2.1, 2.4**
    - Add `tests/test_lineage_record.py`; write a `st.composite` strategy `lineage_record()` generating valid UUID4 run_ids, ISO timestamps, 40-char hex git SHAs, `module:fn` refs, path lists, statuses
    - `# Feature: file-pipeline-lineage, Property 4: LineageStore save/load round-trip`

- [x] 3. Implement `LineageStore`
  - [x] 3.1 Create `src/file_pipeline_lineage/store.py` with `LineageStore.__init__`, `save`, `load`, `list_run_ids`
    - `save` uses atomic write: `NamedTemporaryFile(dir=store_root)` → flush/fsync → `os.replace`
    - `load` raises `RunNotFoundError` (message includes `run_id`) if file absent; raises `LineageError` wrapping `json.JSONDecodeError` on bad JSON
    - `list_run_ids` returns `[p.stem for p in store_root.glob("*.json")]`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.2, 7.3_

  - [x] 3.2 Write property test for `LineageStore` save/load round-trip (Property 4)
    - **Property 4: LineageStore save/load round-trip**
    - **Validates: Requirements 2.1, 2.4**
    - `# Feature: file-pipeline-lineage, Property 4: LineageStore save/load round-trip`
    - Add `tests/test_lineage_store.py`

  - [x] 3.3 Write property test for distinct storage paths (Property 5)
    - **Property 5: Distinct Run_IDs get distinct storage paths**
    - **Validates: Requirements 2.2, 7.2**
    - `# Feature: file-pipeline-lineage, Property 5: Distinct Run_IDs get distinct storage paths`

  - [x] 3.4 Write property test for `RunNotFoundError` on missing run_id (Property 6)
    - **Property 6: Missing Run_ID raises RunNotFoundError**
    - **Validates: Requirements 2.5**
    - `# Feature: file-pipeline-lineage, Property 6: Missing Run_ID raises RunNotFoundError`

  - [x] 3.5 Write property test for `list_run_ids` completeness (Property 7)
    - **Property 7: list_run_ids returns exactly the saved Run_IDs**
    - **Validates: Requirements 2.6**
    - `# Feature: file-pipeline-lineage, Property 7: list_run_ids returns exactly the saved Run_IDs`

- [x] 4. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement `RunContext` and `ReplayContext`
  - [x] 5.1 Create `src/file_pipeline_lineage/context.py` with `RunContext`
    - Constructor accepts `run_id: str` and `base_output_dir: Path`
    - `open_input(path, mode="r", **kwargs)` records `str(path)` in `_inputs`, delegates to `open()`
    - `open_output(path, mode="w", **kwargs)` resolves to `base_output_dir / run_id / Path(path).name`, creates parent dirs, records resolved path in `_outputs`, delegates to `open()`
    - `run_id`, `inputs`, `outputs` properties return immutable views
    - _Requirements: 1.6, 7.4_

  - [x] 5.2 Add `ReplayContext` to `context.py` as a subclass of `RunContext`
    - Constructor additionally accepts `orig_run_id: str` and `replay_root: Path`
    - Overrides `open_output` to resolve to `replay_root / orig_run_id / run_id / Path(path).name`
    - _Requirements: 3.3, 4.1, 4.2_

  - [x] 5.3 Write property test for `RunContext` output path construction (Property 10)
    - **Property 10: RunContext constructs output paths under base_output_dir/run_id**
    - **Validates: Requirements 7.4**
    - `# Feature: file-pipeline-lineage, Property 10: RunContext constructs output paths under base_output_dir/run_id`
    - Add `tests/test_tracker.py` (context tests can live here alongside tracker tests)

  - [x] 5.4 Write property test for `ReplayContext` output path isolation (Property 9)
    - **Property 9: Replay output directory contains both run IDs**
    - **Validates: Requirements 3.3, 4.1, 4.2**
    - `# Feature: file-pipeline-lineage, Property 9: Replay output directory contains both run IDs`

- [x] 6. Implement `Tracker`
  - [x] 6.1 Create `src/file_pipeline_lineage/tracker.py` with `Tracker.__init__` and `track`
    - `track` assigns UUID4 `run_id`, calls `git rev-parse HEAD` via `subprocess.run`; raises `LineageError` if not a git repo or no commits
    - Derives `function_ref` as `fn.__module__ + ":" + fn.__qualname__`
    - Constructs `RunContext(run_id, base_output_dir)`, calls `fn(ctx)`
    - On success: builds `LineageRecord(status="success", exception_message=None, original_run_id=None, ...)` from `ctx.inputs`/`ctx.outputs`, saves to store, returns record
    - On exception: builds `LineageRecord(status="failed", exception_message=str(e), ...)` from `ctx.outputs` at exception time, saves to store, re-raises
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 5.1, 5.2, 7.1, 7.4_

  - [x] 6.2 Write property test for `LineageRecord` completeness on success (Property 1)
    - **Property 1: LineageRecord completeness**
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.6**
    - `# Feature: file-pipeline-lineage, Property 1: LineageRecord completeness`

  - [x] 6.3 Write property test for Run_ID uniqueness (Property 2)
    - **Property 2: Run_ID uniqueness**
    - **Validates: Requirements 1.2, 7.1**
    - `# Feature: file-pipeline-lineage, Property 2: Run_ID uniqueness`

  - [x] 6.4 Write property test for failed run partial outputs and re-raise (Property 3)
    - **Property 3: Failed run captures partial outputs and re-raises**
    - **Validates: Requirements 1.5**
    - `# Feature: file-pipeline-lineage, Property 3: Failed run captures partial outputs and re-raises`

  - [x] 6.5 Write property test for git_commit and function_ref capture (Property 14)
    - **Property 14: git_commit and function_ref are captured correctly**
    - **Validates: Requirements 5.1, 5.2**
    - `# Feature: file-pipeline-lineage, Property 14: git_commit and function_ref are captured correctly`
    - Uses the temporary git repository pytest fixture (see task 7.1)

- [x] 7. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement `Replayer`
  - [x] 8.1 Create `src/file_pipeline_lineage/replayer.py` with `Replayer.__init__` and `replay`
    - `replay` loads record from store; raises `MissingInputError` (listing all absent paths) if any `input_paths` are missing — no execution occurs
    - Runs `git worktree add <tmpdir> <git_commit>`; raises `MissingCommitError` if the command fails due to unknown commit
    - Prepends tmpdir to `sys.path`, imports function via `importlib.import_module` + `getattr` using `function_ref` (`module:fn` split on `":"`)
    - Constructs `ReplayContext(replay_run_id, base_output_dir=replay_root, orig_run_id=record.run_id, replay_root=replay_root)` and calls `fn(ctx)`
    - Cleans up worktree via `git worktree remove --force <tmpdir>` in a `finally` block; restores `sys.path`
    - Saves and returns new `LineageRecord` with `original_run_id=record.run_id`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.4, 5.5_

  - [x] 8.2 Add `conftest.py` fixture `git_repo` in `tests/` that initialises a real git repo in `tmp_path`, writes and commits a simple pipeline function (`simple_pipeline(ctx)`), and exposes `(repo_path, commit_sha, function_ref)` for replay tests
    - _Requirements: 3.2, 5.4_

  - [x] 8.3 Write property test for replay output path isolation (Property 9 — Replayer side)
    - **Property 9: Replay output directory contains both run IDs**
    - **Validates: Requirements 3.3, 4.1, 4.2**
    - `# Feature: file-pipeline-lineage, Property 9: Replay output directory contains both run IDs`
    - Add `tests/test_replayer.py`; use `git_repo` fixture

  - [x] 8.4 Write property test for replay record references original run_id (Property 11)
    - **Property 11: Replay record references original run_id**
    - **Validates: Requirements 3.4**
    - `# Feature: file-pipeline-lineage, Property 11: Replay record references original run_id`

  - [x] 8.5 Write property test for `MissingInputError` before execution (Property 12)
    - **Property 12: Missing inputs raise MissingInputError before execution**
    - **Validates: Requirements 3.5**
    - `# Feature: file-pipeline-lineage, Property 12: Missing inputs raise MissingInputError before execution`

  - [x] 8.6 Write property test for prior outputs preserved after replay (Property 13)
    - **Property 13: Prior outputs are preserved after replay**
    - **Validates: Requirements 4.3**
    - `# Feature: file-pipeline-lineage, Property 13: Prior outputs are preserved after replay`

  - [x] 8.7 Write property test for replay produces equivalent outputs (Property 8)
    - **Property 8: Replay produces equivalent outputs**
    - **Validates: Requirements 3.2, 5.4**
    - `# Feature: file-pipeline-lineage, Property 8: Replay produces equivalent outputs`
    - Uses `git_repo` fixture; compare replay output content against re-running the same function directly

- [x] 9. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Wire public API and write unit + integration tests
  - [x] 10.1 Update `src/file_pipeline_lineage/__init__.py` to export all public names: `RunContext`, `ReplayContext`, `LineageRecord`, `LineageStore`, `Tracker`, `Replayer`, `LineageError`, `RunNotFoundError`, `MissingInputError`, `MissingCommitError`
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 10.2 Write unit tests in `tests/test_lineage_store.py` for error conditions
    - Test `RunNotFoundError` message contains the missing `run_id`
    - Test `LineageError` is raised on corrupt JSON
    - _Requirements: 2.5_

  - [x] 10.3 Write unit tests in `tests/test_tracker.py` for success and failure paths
    - Test a known pipeline function produces a `LineageRecord` with expected field values
    - Test `LineageError` is raised when not in a git repo
    - _Requirements: 1.1, 1.5, 5.1_

  - [x] 10.4 Write unit tests in `tests/test_replayer.py` for error conditions
    - Test `MissingInputError` lists all absent paths and does not create output files
    - Test `MissingCommitError` is raised for an unknown commit SHA
    - _Requirements: 3.5, 5.5_

  - [x] 10.5 Write end-to-end integration test in `tests/test_integration.py`
    - Track a pipeline → load record from store → replay → assert replay record has `original_run_id` set, output paths are distinct, both output files exist on disk
    - Uses `git_repo` fixture
    - _Requirements: 1.1, 3.2, 3.3, 3.4, 4.1, 4.3_

- [x] 11. Write demo script and smoke test
  - [x] 11.1 Create `demo.py` at project root
    - Defines a simple pipeline function using `ctx.open_input` / `ctx.open_output`
    - Calls `Tracker.track(fn, base_output_dir)`, prints `run_id`
    - Calls `Replayer.replay(run_id)`, prints replay `run_id` and output location
    - Verifies both original and replay output files exist and prints confirmation
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 11.2 Write smoke test in `tests/test_demo.py`
    - Run `demo.py` via `subprocess.run(["python", "demo.py"], ...)` inside a temp git repo
    - Assert exit code 0 and stdout contains expected substrings (run_id, replay run_id, confirmation message)
    - _Requirements: 6.2, 6.3, 6.4_

- [x] 12. Finalise `INTERFACES.md` and `README.md`
  - [x] 12.1 Update `INTERFACES.md` with complete public API documentation: all class signatures, method signatures with type annotations, exception hierarchy, `LineageRecord` field table, JSON schema summary, and disk layout diagram
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 12.2 Create `README.md` with installation instructions (`uv pip install -e .`), quick-start code example, and link to `INTERFACES.md`
    - _Requirements: 6.1_

- [x] 13. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required — no optional tasks
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `@given` + `@settings(max_examples=200)` and carry the `# Feature: file-pipeline-lineage, Property N: ...` comment tag
- The `git_repo` pytest fixture (task 8.2) is required by Properties 8 and 14 and the integration test
- Checkpoints at tasks 4, 7, 9, and 13 ensure incremental validation throughout the build
