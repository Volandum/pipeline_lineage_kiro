# Requirements Document — Demo Notebook

## Table of Contents

- [Introduction](#introduction)
- [Glossary](#glossary)
- [Requirements](#requirements)
  - [Requirement 1: Self-Contained Execution Environment](#requirement-1-self-contained-execution-environment)
  - [Requirement 2: Simulated Database Connection](#requirement-2-simulated-database-connection)
  - [Requirement 3: Simulated S3 Connection](#requirement-3-simulated-s3-connection)
  - [Requirement 4: Pipeline Function Definition](#requirement-4-pipeline-function-definition)
  - [Requirement 5: Pandas Processing Step](#requirement-5-pandas-processing-step)
  - [Requirement 6: Lineage Tracking](#requirement-6-lineage-tracking)
  - [Requirement 7: Lineage Record Review](#requirement-7-lineage-record-review)
  - [Requirement 8: Replay Execution](#requirement-8-replay-execution)
  - [Requirement 9: Replay Correctness Verification](#requirement-9-replay-correctness-verification)
  - [Requirement 10: Mock Behaviour Callout](#requirement-10-mock-behaviour-callout)
  - [Requirement 11: Notebook Structure and Navigability](#requirement-11-notebook-structure-and-navigability)

---

## Introduction

A self-contained, fully-runnable Jupyter notebook that demonstrates the end-to-end
capabilities of the `file_pipeline_lineage` package. The notebook simulates a realistic
data pipeline: loading records from a database source, processing them with Pandas, and
writing results to an S3-like sink — all without requiring any real cloud resources.

All demo files live under a `demo/` subfolder at the project root. Custom `Connection`
subclasses simulate the database (SQLite in-memory) and S3 (local filesystem acting as a
fake bucket). The notebook then shows the captured `LineageRecord` and demonstrates that
replay produces identical outputs.

---

## Glossary

- **Notebook**: The Jupyter notebook file (`demo/demo_notebook.ipynb`) inside the `demo/` subfolder.
- **Demo_Subfolder**: The `demo/` directory at the project root containing all demo artefacts: the notebook, the pipeline module, and any supporting files.
- **SimulatedDBConnection**: A `Connection` subclass backed by a file-based SQLite
  database seeded with example data by the notebook setup cell and removed by the cleanup cell.
- **MockS3Connection**: A `Connection` subclass that wraps `S3Connection` with a mocked
  boto3 client (via `unittest.mock`), so the demo exercises the real `S3Connection` code
  path without requiring AWS credentials or network access.
- **Pipeline_Function**: The module-level Python function passed to `Tracker.track()`;
  must be importable by `function_ref` for replay to work.
- **Tracker**: The `file_pipeline_lineage.Tracker` class that wraps a pipeline function,
  captures lineage, and saves a `LineageRecord`.
- **Replayer**: The `file_pipeline_lineage.Replayer` class that loads a `LineageRecord`
  and re-executes the pipeline.
- **LineageRecord**: The frozen dataclass capturing all metadata about a single run.
- **LineageStore**: The persistence layer that saves and loads `LineageRecord` JSON files.
- **RunContext**: The I/O interception object passed to every pipeline function.

---

## Requirements

### Requirement 1: Self-Contained Execution Environment

**User Story:** As a developer evaluating the package, I want to run the notebook from
top to bottom without configuring any external services, so that I can understand the
package's capabilities immediately.

#### Acceptance Criteria

1. THE Notebook SHALL require only packages already declared in `pyproject.toml` plus
   `jupyter` and `pandas` (no boto3, no cloud SDKs, no external databases).
2. ALL demo artefacts (notebook, pipeline module, supporting files) SHALL reside under a
   `demo/` subfolder at the project root. No demo files SHALL be placed at the project root.
3. THE Notebook SHALL create all temporary directories and seed data programmatically
   within notebook cells, so that no manual setup step is required before running.
4. WHEN the notebook is executed from top to bottom in a clean environment, THE Notebook
   SHALL complete without raising any unhandled exceptions.
5. THE Notebook SHALL clean up all temporary files and directories it creates, either
   within a dedicated cleanup cell or via Python context managers.

---

### Requirement 2: Simulated Database Connection

**User Story:** As a developer, I want a realistic database-like source connection, so
that the demo reflects a real-world pipeline pattern rather than plain file reads.

#### Acceptance Criteria

1. THE SimulatedDBConnection SHALL subclass `file_pipeline_lineage.Connection`.
2. THE SimulatedDBConnection SHALL implement `atomic_read(timestamp_utc=None)` to query a
   file-based SQLite database and return a `pandas.DataFrame` (all rows at once).
3. THE SimulatedDBConnection SHALL implement `serialise()` to return a JSON-serialisable
   `dict` containing only the database file path (no credentials or runtime state).
4. WHEN `SimulatedDBConnection(**conn.serialise())` is called, THE SimulatedDBConnection
   SHALL reconstruct an equivalent connection (round-trip property).
5. THE SimulatedDBConnection SHALL set `supports_time_travel` to `False`.
6. IF `atomic_read()` is called with a non-`None` `timestamp_utc`, THEN THE
   SimulatedDBConnection SHALL raise `UnsupportedOperationError`.
7. THE Notebook setup cell SHALL create the SQLite database file and seed it with example
   records before any pipeline cell runs.
8. THE Notebook cleanup cell SHALL delete the SQLite database file as part of teardown.

---

### Requirement 3: Mocked S3 Connection

**User Story:** As a developer, I want the demo to exercise the real `S3Connection` code
path, so that the notebook demonstrates how the package works with S3 without requiring
AWS credentials or network access.

#### Acceptance Criteria

1. THE MockS3Connection SHALL be a thin wrapper that instantiates `S3Connection` with a
   mocked boto3 client injected via `unittest.mock`, so no real AWS calls are made.
2. THE mock SHALL intercept `put_object` and `head_object` boto3 calls and store written
   data in an in-memory dict keyed by S3 key, simulating a fake bucket.
3. THE MockS3Connection SHALL implement `serialise()` to return the same dict as
   `S3Connection.serialise()` — `{"bucket": ..., "key": ..., "time_travel": false}`.
4. WHEN `MockS3Connection(**conn.serialise())` is called, THE MockS3Connection SHALL
   reconstruct an equivalent connection (round-trip property).
5. THE MockS3Connection SHALL set `supports_time_travel` to `False`.
6. WHEN `atomic_write` is called, THE MockS3Connection SHALL return
   `WriteResult(OverwriteStatus.NO_OVERWRITE)` for a new key and
   `WriteResult(OverwriteStatus.OVERWRITE)` for an existing key.

---

### Requirement 4: Pipeline Function Definition

**User Story:** As a developer, I want the pipeline function to be importable at module
level, so that the Replayer can reconstruct and re-execute it.

#### Acceptance Criteria

1. THE Pipeline_Function SHALL be defined at module level in a Python module inside the
   `demo/` subfolder (e.g. `demo/pipeline.py`), importable as `demo.pipeline` from the
   project root.
2. THE Pipeline_Function SHALL accept a single `RunContext` argument and return `None`.
3. THE Pipeline_Function SHALL read its input exclusively via `ctx.atomic_read()` using
   a `SimulatedDBConnection`, receiving a `pandas.DataFrame` directly.
4. THE Pipeline_Function SHALL write its output exclusively via `ctx.open_output()` or
   `ctx.atomic_write()` using a `SimulatedS3Connection`.
5. THE Pipeline_Function SHALL be committed to the git repository before `Tracker.track()`
   is called, so that `function_ref` resolves to a valid importable path.

---

### Requirement 5: Pandas Processing Step

**User Story:** As a developer, I want to see a realistic data transformation, so that
the demo shows lineage capture working with real data-processing code.

#### Acceptance Criteria

1. THE Pipeline_Function SHALL load the input `DataFrame` from the `SimulatedDBConnection`
   and apply at least one Pandas transformation (e.g. filtering, aggregation, or column
   derivation).
2. THE Pipeline_Function SHALL serialise the transformed `DataFrame` to CSV bytes or a
   CSV string before writing to the `MockS3Connection`.
3. WHEN the same input data is provided, THE Pipeline_Function SHALL produce byte-for-byte
   identical CSV output on every execution (deterministic output property).

---

### Requirement 6: Lineage Tracking

**User Story:** As a developer, I want to see the Tracker capture a complete LineageRecord,
so that I understand what metadata is recorded for each run.

#### Acceptance Criteria

1. WHEN `Tracker.track(Pipeline_Function, output_dir)` is called, THE Tracker SHALL
   return a `LineageRecord` with `status == "success"`.
2. THE LineageRecord SHALL contain exactly one `InputDescriptor` whose `connection_class`
   identifies `SimulatedDBConnection`.
3. THE LineageRecord SHALL contain exactly one `OutputDescriptor` whose `connection_class`
   identifies `MockS3Connection`.
4. THE LineageRecord SHALL contain a non-empty `git_commit` field (40-character hex SHA).
5. THE LineageRecord SHALL contain a `function_ref` field in `"module:qualname"` format
   that resolves to the `Pipeline_Function`.

---

### Requirement 7: Lineage Record Review

**User Story:** As a developer, I want to inspect the captured LineageRecord in the
notebook, so that I can see exactly what was recorded.

#### Acceptance Criteria

1. THE Notebook SHALL display the `LineageRecord` fields in a readable format (e.g.
   pretty-printed JSON or a formatted cell output) after the tracking cell.
2. THE Notebook SHALL display the `InputDescriptor` fields including `name`,
   `connection_class`, `connection_args`, and `access_timestamp`.
3. THE Notebook SHALL display the `OutputDescriptor` fields including `name`,
   `connection_class`, `connection_args`, `overwrite_status`, and both timestamps.
4. THE Notebook SHALL display the path to the saved `LineageRecord` JSON file on disk.

---

### Requirement 8: Replay Execution

**User Story:** As a developer, I want to see the Replayer re-execute the pipeline, so
that I understand how past runs can be reproduced.

#### Acceptance Criteria

1. WHEN `Replayer.replay(run_id)` is called with the original `run_id`, THE Replayer
   SHALL return a `LineageRecord` with `status == "success"`.
2. THE replay `LineageRecord` SHALL have `original_run_id` equal to the original `run_id`.
3. THE replay `LineageRecord` SHALL have a different `run_id` from the original record.
4. THE Notebook SHALL display the replay `LineageRecord` fields after the replay cell,
   using the same readable format as Requirement 7.

---

### Requirement 9: Replay Correctness Verification

**User Story:** As a developer, I want the notebook to assert that replay outputs match
the original outputs, so that I can trust the replay mechanism.

#### Acceptance Criteria

1. WHEN the original and replay output files are compared byte-for-byte, THE Notebook
   SHALL assert that their contents are identical.
2. THE Notebook SHALL display a clear success message (e.g. `"Replay verified: outputs
   match"`) when the assertion passes.
3. THE Notebook SHALL display the original output path and the replay output path side
   by side so the reader can see they are distinct filesystem locations.

---

### Requirement 10: Mock Behaviour Callout

**User Story:** As a developer reading the notebook, I want a clear explanation of how
the S3 mock works and what it means for replay, so that I understand the demo's
limitations and how to adapt it for a real S3 connection.

#### Acceptance Criteria

1. THE Notebook SHALL include a dedicated markdown callout cell in the Custom Connections
   section explaining that `MockS3Connection` uses `unittest.mock` to intercept boto3
   calls and stores written data in an in-memory dict — no real AWS calls are made.
2. THE callout SHALL explain that each `MockS3Connection` instance gets its own isolated
   in-memory store, so the replay's written bytes are not visible in the original run's
   mock instance (and vice versa) — this is intentional and consistent with the
   package's run-isolation guarantee.
3. THE callout SHALL explain that to use a real S3 bucket, the user would replace
   `MockS3Connection` with `S3Connection` and supply valid AWS credentials.
4. THE callout SHALL be visually distinct (e.g. a `> **Note:**` blockquote) so it stands
   out from surrounding prose.

---

### Requirement 11: Notebook Structure and Navigability

**User Story:** As a developer reading the notebook, I want clear section headings and
explanatory prose, so that I can follow the demo without reading source code.

#### Acceptance Criteria

1. THE Notebook SHALL contain a markdown cell at the top with a title and a table of
   contents linking to each major section.
2. THE Notebook SHALL organise cells into named sections: Setup, Custom Connections,
   Pipeline Function, Run the Pipeline, Inspect Lineage, Replay, Verify Replay, Cleanup.
3. WHEN each section heading is rendered, THE Notebook SHALL include a one-paragraph
   prose explanation of what that section demonstrates.
4. THE Notebook SHALL contain no section whose rendered markdown exceeds 30 lines,
   consistent with the project document formatting convention.
