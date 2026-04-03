# Implementation Plan: demo-notebook

## Overview

Create the `demo/` package with `SimulatedDBConnection`, `MockS3Connection`, and
`run_pipeline` in `demo/pipeline.py`, then build `demo/demo_notebook.ipynb` that
exercises the full `file_pipeline_lineage` stack end-to-end — tracking, lineage
inspection, replay, and byte-for-byte verification — without any real cloud services.
Unit and property tests live in `demo/tests/test_demo_connections.py` and
`demo/tests/test_demo_properties.py`.

## Tasks

- [x] 1. Create the `demo/` package skeleton
  - Create `demo/__init__.py` (empty, makes `demo` importable as a package).
  - Create `demo/pipeline.py` with a module-level `DB_PATH = ""` placeholder and stub
    imports (`pandas`, `file_pipeline_lineage`).
  - _Requirements: 1.2, 4.1_
  - Commit: `feat: task 1 — create demo/ package skeleton`

- [ ] 2. Implement `SimulatedDBConnection` in `demo/pipeline.py`
  - [x] 2.1 Implement `SimulatedDBConnection(Connection)`
    - `__init__(self, db_path: str)` — stores `self.db_path = db_path`.
    - `atomic_read(timestamp_utc=None)` — opens the SQLite file via `sqlite3`, runs
      `SELECT * FROM records`, returns a `pandas.DataFrame`; raises
      `UnsupportedOperationError` if `timestamp_utc` is not `None`.
    - `serialise()` returns `{"db_path": str(self.db_path)}`.
    - `supports_time_travel = False`.
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [x] 2.2 Write unit tests for `SimulatedDBConnection` in `demo/tests/test_demo_connections.py`
    - Test `atomic_read(None)` returns a `DataFrame` with expected columns and rows.
    - Test `atomic_read(timestamp)` raises `UnsupportedOperationError`.
    - Test `serialise()` returns `{"db_path": ...}`.
    - _Requirements: 2.2, 2.3, 2.6_

  - [x] 2.3 Write property test for `SimulatedDBConnection` serialise round-trip
    - **Property 1: SimulatedDBConnection serialise round-trip**
    - For any `db_path` string, `SimulatedDBConnection(**conn.serialise()).serialise()`
      must equal `conn.serialise()`.
    - **Validates: Requirements 2.3, 2.4**

  - Commit: `feat: task 2 — implement SimulatedDBConnection`

- [ ] 3. Implement `MockS3Connection` in `demo/pipeline.py`
  - [~] 3.1 Implement `MockS3Connection(Connection)`
    - `__init__(self, bucket: str, key: str, time_travel: bool = False)` — stores args;
      creates a fresh `MagicMock` boto3 client; sets up `head_object` / `put_object`
      side-effects to store data in an in-memory `dict` keyed by S3 key.
    - `atomic_write(data, run_id, overwrite=False)` — delegates to an internal
      `S3Connection` instance whose `_s3` client is replaced with the mock; returns
      `WriteResult(NO_OVERWRITE)` for a new key and `WriteResult(OVERWRITE)` for an
      existing key.
    - `serialise()` returns `{"bucket": self.bucket, "key": self.key, "time_travel": self.time_travel}`.
    - `supports_time_travel = False`.
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [~] 3.2 Write unit tests for `MockS3Connection` in `demo/tests/test_demo_connections.py`
    - Test `atomic_write` returns `NO_OVERWRITE` on first write, `OVERWRITE` on second.
    - Test `serialise()` shape matches `S3Connection.serialise()`.
    - _Requirements: 3.3, 3.6_

  - [~] 3.3 Write property test for `MockS3Connection` serialise round-trip
    - **Property 2: MockS3Connection serialise round-trip**
    - For any `bucket`, `key`, and `time_travel` values,
      `MockS3Connection(**conn.serialise()).serialise()` must equal `conn.serialise()`.
    - **Validates: Requirements 3.3, 3.4**

  - [~] 3.4 Write property test for `MockS3Connection` overwrite status
    - **Property 4: MockS3Connection overwrite status is correct**
    - For any `MockS3Connection`, writing to a new key returns `NO_OVERWRITE`; writing
      to the same key a second time returns `OVERWRITE`.
    - **Validates: Requirements 3.6**

  - Commit: `feat: task 3 — implement MockS3Connection`

- [~] 4. Add `ConnectionContractTests` subclasses in `tests/test_demo_connections.py`
  - Subclass `ConnectionContractTests` for `SimulatedDBConnection` (with a temp SQLite
    DB seeded in `make_connection()`).
  - Subclass `ConnectionContractTests` for `MockS3Connection`.
  - _Requirements: 2.1, 3.1_
  - Commit: `feat: task 4 — ConnectionContractTests subclasses for demo connections`

- [ ] 5. Implement `run_pipeline` in `demo/pipeline.py`
  - [~] 5.1 Implement `run_pipeline(ctx: RunContext) -> None`
    - `df = ctx.atomic_read(SimulatedDBConnection(DB_PATH))`.
    - Filter: `transformed = df[df["value"] > 0].copy()`.
    - Derive column: `transformed["label"] = transformed["value"].astype(str)`.
    - Serialise: `csv_bytes = transformed.to_csv(index=False).encode()`.
    - Write: `ctx.atomic_write(MockS3Connection("demo-bucket", "output/results.csv"), csv_bytes)`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [~] 5.2 Write property test for pipeline output determinism
    - **Property 3: Pipeline output is deterministic**
    - For any input `DataFrame`, calling `run_pipeline` twice with the same data must
      produce byte-for-byte identical CSV output.
    - **Validates: Requirements 5.3**

  - Commit: `feat: task 5 — implement run_pipeline`

- [~] 6. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Build `demo/demo_notebook.ipynb`
  - [~] 7.1 Create notebook with Title + TOC and Setup section
    - Markdown cell: title, table of contents linking to each section.
    - Code cell: create temp dir, create SQLite DB at a temp path, seed with
      `INSERT INTO records VALUES (1, 10.5, 'a'), (2, -3.0, 'b'), (3, 7.2, 'c')`,
      set module-level `demo.pipeline.DB_PATH`, create `LineageStore`.
    - _Requirements: 1.3, 2.7, 11.1, 11.2, 11.3_

  - [~] 7.2 Add Custom Connections section with mock behaviour callout
    - Code cell: import `SimulatedDBConnection` and `MockS3Connection` from `demo.pipeline`.
    - Markdown callout cell (`> **Note:**` blockquote) explaining: mock intercepts boto3
      calls, stores data in-memory, each instance has its own isolated store, and how to
      swap in a real `S3Connection`.
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [~] 7.3 Add Pipeline Function, Git commit, and Run the Pipeline sections
    - Code cell: import `run_pipeline` from `demo.pipeline`.
    - Code cell: `git add demo/pipeline.py demo/__init__.py; git commit -m "..."` to
      ensure `demo/pipeline.py` is committed before `Tracker.track()`.
    - Code cell: `tracker.track(run_pipeline, output_dir)`, capture `record`.
    - _Requirements: 4.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [~] 7.4 Add Inspect Lineage section
    - Code cell: pretty-print `record` as JSON (`json.dumps(record.to_dict(), indent=2)`).
    - Display `InputDescriptor` fields: `name`, `connection_class`, `connection_args`,
      `access_timestamp`.
    - Display `OutputDescriptor` fields: `name`, `connection_class`, `connection_args`,
      `overwrite_status`, both timestamps.
    - Display path to saved `LineageRecord` JSON file.
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [~] 7.5 Add Replay, Verify Replay, and Cleanup sections
    - Code cell: `replayer.replay(record.run_id)`, capture `replay_record`.
    - Code cell: display `replay_record` fields; assert `original_run_id == record.run_id`;
      assert `replay_record.run_id != record.run_id`.
    - Code cell: read original and replay output bytes; assert byte-for-byte equality;
      print `"Replay verified: outputs match"` and both output paths.
    - Code cell: `shutil.rmtree(..., ignore_errors=True)` and `Path.unlink(missing_ok=True)`
      to remove SQLite DB and temp dirs.
    - _Requirements: 1.5, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3_

  - Commit: `feat: task 7 — build demo_notebook.ipynb`

- [ ] 8. Write integration property tests in `demo/tests/test_demo_properties.py`
  - [~] 8.1 Write property test for Tracker producing a complete LineageRecord
    - **Property 5: Tracker produces a complete LineageRecord**
    - For any valid `db_path` and pipeline execution, the returned `LineageRecord` must
      have `status == "success"`, exactly one input descriptor identifying
      `SimulatedDBConnection`, exactly one output descriptor identifying
      `MockS3Connection`, a 40-char hex `git_commit`, and a `function_ref` in
      `"module:qualname"` format.
    - Tag `@pytest.mark.integration`; skip if not in a git repo.
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

  - [~] 8.2 Write property test for Replay producing matching outputs
    - **Property 6: Replay produces matching outputs**
    - For any original run, `Replayer.replay(run_id)` must produce a `LineageRecord`
      with `status == "success"`, `original_run_id` equal to the original `run_id`, a
      distinct `run_id`, and output bytes identical to the original run's output bytes.
    - Tag `@pytest.mark.integration`; skip if not in a git repo.
    - **Validates: Requirements 8.1, 8.2, 8.3, 9.1**

  - Commit: `feat: task 8 — integration property tests for Tracker and Replayer`

- [~] 9. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Properties 5 and 6 require a real git repo with `demo/pipeline.py` committed; they are
  tagged `@pytest.mark.integration` and should be skipped in environments without git
- `DB_PATH` is a module-level variable in `demo/pipeline.py` set by the notebook before
  `Tracker.track()` is called — the notebook must set it before running the pipeline cell
- The mock boto3 client is created fresh in each `MockS3Connection.__init__`, so replay
  reconstruction works without any stored credentials or state
