# Implementation Plan: generalised-connections

## Overview

Introduce the `Connection` ABC and built-in connectors (`LocalConnection`, `S3Connection`),
restructure `LineageRecord` to use named descriptors, update `RunContext`/`ReplayContext`
for connection-based I/O, extend `Replayer` with `importlib` reconstruction and time-travel
routing, add five new exception types, ship `ConnectionContractTests`, and migrate all
existing code that touches the breaking changes.

Tasks are ordered so foundational pieces (exceptions → descriptors → Connection ABC →
`LineageRecord`) land before the components that depend on them (`RunContext`, `Tracker`,
`Replayer`), and migration/test updates come last.

## Tasks

- [ ] 1. Add new exception classes to `exceptions.py`
  - Add `UnsupportedOperationError`, `TimeTravelError`, `ConflictError`,
    `ConfigurationError`, and `DuplicateNameError` as subclasses of `LineageError`
    alongside the four existing exception classes.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_
  - Commit: `feat: task 1 — add five new exception classes`

- [x] 2. Create `src/file_pipeline_lineage/connections.py` — core types
  - [x] 2.1 Implement `OverwriteStatus` enum and `WriteResult` frozen dataclass
    - `OverwriteStatus(str, Enum)` with values `OVERWRITE`, `NO_OVERWRITE`, `UNKNOWN`,
      `IN_PROGRESS` serialising to lowercase strings.
    - `WriteResult(frozen=True)` with single field `overwrite_status: OverwriteStatus`.
    - _Requirements: 7.1, 7.2, 7.4, 7.9_

  - [x] 2.2 Write unit tests for `WriteResult` / `OverwriteStatus` in `tests/test_write_result.py`
    - Verify each `OverwriteStatus` value serialises to the expected lowercase string.
    - Verify `WriteResult` is frozen (immutable).
    - _Requirements: 7.9_

  - [x] 2.3 Implement `Connection` ABC
    - `Connection(ABC)` with no abstract methods; all four I/O methods default to raising
      `UnsupportedOperationError`; concrete `serialise()` using `inspect.signature`;
      `supports_time_travel` property returning `False`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 2.4 Implement `LocalConnection`
    - Constructor: `__init__(self, path: str | Path, base_output_dir: str | Path | None = None)`.
    - `read(timestamp_utc=None)`: opens path for reading; raises `UnsupportedOperationError`
      if `timestamp_utc` is not `None`.
    - `write(run_id, overwrite=False)`: returns a context manager; `__enter__` checks for
      conflict when `overwrite=False` (raises `ConflictError`), opens file, yields;
      `__exit__` (success) closes file and resolves final `OverwriteStatus`; `__exit__`
      (exception) closes/removes partial file.
    - `atomic_read` and `atomic_write` raise `UnsupportedOperationError`.
    - `serialise()` returns `{"path": "<absolute path string>"}`.
    - `supports_time_travel` returns `False`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.5 Implement `S3Connection` (reference)
    - Constructor: `__init__(self, bucket: str, key: str, time_travel: bool = False)`.
    - `read(timestamp_utc=None)`: streaming download; time-travel via S3 Object Versioning
      when `timestamp_utc` is not `None`; raises `TimeTravelError` if no version found;
      raises `ConfigurationError` if versioning not enabled.
    - `atomic_write(data, run_id, overwrite=False)`: single PUT to `<run_id>/<key_filename>`;
      returns `WriteResult` with `OVERWRITE` or `NO_OVERWRITE`.
    - `write` and `atomic_read` raise `UnsupportedOperationError`.
    - `serialise()` returns `{"bucket": ..., "key": ..., "time_travel": bool}` — no credentials.
    - `supports_time_travel` returns `self.time_travel`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - Commit: `feat: task 2 — Connection ABC, LocalConnection, S3Connection, WriteResult`

- [x] 3. Create `src/file_pipeline_lineage/descriptors.py`
  - Implement `InputDescriptor` frozen dataclass with fields: `name`, `connection_class`,
    `connection_args`, `access_timestamp`, `time_travel`.
  - Implement `OutputDescriptor` frozen dataclass with fields: `name`, `connection_class`,
    `connection_args`, `overwrite_requested`, `overwrite_status`.
  - Add `to_dict()` / `from_dict()` class methods to each for JSON round-trip.
  - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - Commit: `feat: task 3 — InputDescriptor and OutputDescriptor dataclasses`

- [x] 4. Update `LineageRecord` in `record.py`
  - Replace `input_paths: tuple[str, ...]` and `output_paths: tuple[str, ...]` with
    `inputs: tuple[InputDescriptor, ...]` and `outputs: tuple[OutputDescriptor, ...]`.
  - Update `to_dict()` to serialise descriptors as JSON arrays of objects.
  - Update `from_dict()` to reconstruct descriptors via `InputDescriptor.from_dict` /
    `OutputDescriptor.from_dict`.
  - _Requirements: 9.1, 9.2, 9.4, 9.5_

  - [x] 4.1 Write property test for `LineageRecord` round-trip in `tests/test_lineage_record.py`
    - **Property 1: LineageRecord round-trip**
    - Replace the existing `lineage_record` strategy to generate records with
      `InputDescriptor` / `OutputDescriptor` lists; assert
      `LineageRecord.from_dict(record.to_dict()) == record`.
    - **Validates: Requirements 9.4, 9.5**

  - Commit: `feat: task 4 — restructure LineageRecord with descriptor fields`

- [x] 5. Update `RunContext` and `ReplayContext` in `context.py`
  - [x] 5.1 Rewrite `RunContext` to accept `Connection` objects
    - New method signatures: `open_input(connection, name=None)`,
      `atomic_read(connection, name=None)`, `open_output(connection, name=None, overwrite=False)`,
      `atomic_write(connection, data, name=None, overwrite=False)`.
    - `open_input`: calls `connection.read(None)`, records `access_timestamp` (UTC now),
      auto-generates name if `None`, raises `DuplicateNameError` on collision, appends
      `InputDescriptor` to `_inputs`.
    - `atomic_read`: same as `open_input` but calls `connection.atomic_read(None)`.
    - `open_output`: calls `connection.write(run_id, overwrite)`, immediately appends
      `OutputDescriptor` with `overwrite_status="in_progress"`, returns context manager;
      on `__exit__` (success) updates descriptor to final status.
    - `atomic_write`: calls `connection.atomic_write(data, run_id, overwrite)`, records
      `WriteResult | None` (maps `None` → `UNKNOWN`).
    - `ctx.inputs` returns `tuple[InputDescriptor, ...]`; `ctx.outputs` returns
      `tuple[OutputDescriptor, ...]`.
    - Auto-name format: `<1-based-index>:<ClassName>(<truncated_params>)`, max 50 chars
      with trailing `...` if truncated.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4,
      7.5, 7.6, 7.7, 7.8_

  - [x] 5.2 Write property test for auto-generated name format
    - **Property 4: Auto-generated name format**
    - For any sequence of `open_input` / `open_output` calls without explicit names,
      each auto-generated name matches `<index>:<ClassName>(...)`, is at most 50 chars,
      and no two names within the same run are equal.
    - **Validates: Requirements 6.1, 6.2**

  - [x] 5.3 Write property test for input descriptor completeness
    - **Property 2: Input descriptor completeness**
    - For any `Connection` passed to `ctx.open_input` or `ctx.atomic_read`, the recorded
      descriptor contains the correct `name`, `connection_class`, `connection_args`,
      a valid ISO-8601 UTC `access_timestamp`, and `time_travel: false`.
    - **Validates: Requirements 5.5, 5.6, 5.9, 9.1, 9.3**

  - [x] 5.4 Write property test for output descriptor completeness
    - **Property 3: Output descriptor completeness**
    - For any `Connection` passed to `ctx.open_output`, the descriptor has
      `overwrite_status: "in_progress"` while the context manager is open and a final
      status (not `"in_progress"`) after `__exit__` completes.
    - **Validates: Requirements 5.4, 7.5, 7.6, 7.7, 7.9, 9.2, 9.3**

  - [x] 5.5 Rewrite `ReplayContext` to reconstruct connections and apply time-travel routing
    - Override `open_input` and `atomic_read` to accept an `InputDescriptor`; reconstruct
      the `Connection` via `importlib`; if `connection.supports_time_travel` call
      `connection.read(descriptor.access_timestamp)` and record `time_travel: true`,
      otherwise call `connection.read(None)` and record `time_travel: false`.
    - Raise `UnsupportedOperationError` if time-travel is requested on a non-supporting
      connection (Req 4.6).
    - _Requirements: 4.6, 8.1, 8.2, 8.3, 8.4_

  - [x] 5.6 Write property test for time-travel routing
    - **Property 5: Time-travel routing**
    - For any `ReplayContext` replaying a run, each input descriptor with
      `supports_time_travel=True` must be called with `access_timestamp`; each with
      `False` must be called with `None`. Replay descriptor records `time_travel`
      accordingly.
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - Commit: `feat: task 5 — update RunContext and ReplayContext for Connection objects`

- [~] 6. Update `tracker.py` to use new `LineageRecord` shape
  - Replace `input_paths=ctx.inputs` / `output_paths=ctx.outputs` with
    `inputs=ctx.inputs` / `outputs=ctx.outputs` in both the success and failure
    `LineageRecord` constructions.
  - _Requirements: 9.1, 9.2_
  - Commit: `feat: task 6 — update Tracker to use descriptor-based LineageRecord`

- [~] 7. Update `replayer.py` — `importlib` reconstruction and time-travel routing
  - Replace `record.input_paths` validation loop with iteration over `record.inputs`
    descriptors; reconstruct each `Connection` via
    `importlib.import_module` + `getattr` + `cls(**descriptor.connection_args)`;
    raise `ConfigurationError` on import or construction failure.
  - Pass reconstructed input connections to `ReplayContext` for time-travel routing.
  - Reconstruct output connections from `record.outputs` descriptors and pass to
    `ReplayContext.open_output`.
  - Build the replay `LineageRecord` with `inputs=ctx.inputs` / `outputs=ctx.outputs`.
  - _Requirements: 10.1, 10.2, 10.4, 10.5_

  - [~] 7.1 Write property test for connection reconstruction round-trip
    - **Property 6: Connection reconstruction round-trip**
    - For any `Connection` instance `c`, `cls(**c.serialise())` (class loaded via
      `importlib`) must produce a connection whose `serialise()` equals `c.serialise()`.
    - **Validates: Requirements 10.1, 10.3**

  - Commit: `feat: task 7 — update Replayer with importlib reconstruction and time-travel`

- [ ] 8. Create `tests/test_connections.py` — contract tests and property tests
  - [~] 8.1 Implement `ConnectionContractTests` base class
    - Abstract `make_connection() -> Connection` method.
    - Capability-aware tests: `serialise()` returns JSON-serialisable dict; round-trip
      `cls(**connection.serialise()).serialise() == connection.serialise()`; `supports_time_travel`
      returns `bool`; `read(None)` returns readable object (if supported); `write(run_id)`
      context manager completes with final `overwrite_status` (if supported);
      `atomic_write(data, run_id)` returns `WriteResult | None` with valid status (if supported);
      two distinct `run_id` values produce non-overlapping output addresses (if supported).
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10_

  - [~] 8.2 Implement `LocalConnectionContractTests(ConnectionContractTests)`
    - `make_connection()` returns a `LocalConnection` pointing at a temp file.
    - Serves as the reference demo of correct `ConnectionContractTests` usage.
    - _Requirements: 12.11_

  - [~] 8.3 Implement `S3ConnectionContractTests(ConnectionContractTests)`
    - `make_connection()` returns an `S3Connection` configured for a mock/stub S3 backend.
    - _Requirements: 12.12_

  - [~] 8.4 Write property test for `LocalConnection` write path structure
    - **Property 7: LocalConnection write path structure**
    - For any `LocalConnection` and any `run_id`, `connection.write(run_id)` must create
      the output file at a path whose components include `run_id` as a directory segment.
    - **Validates: Requirements 2.3, 7.1**

  - [~] 8.5 Write property test for `LocalConnection` read round-trip
    - **Property 8: LocalConnection read round-trip**
    - For any file content written to a path, `LocalConnection(path).read(None)` must
      return a file-like object whose content equals the original.
    - **Validates: Requirements 2.2**

  - [~] 8.6 Write property test for `IN_PROGRESS` → final status transition
    - **Property 9: IN_PROGRESS transitions to final status**
    - For any `LocalConnection` and any `run_id`, the output descriptor has
      `overwrite_status: "in_progress"` while the context manager is open and
      `"no_overwrite"` or `"overwrite"` after `__exit__` completes.
    - **Validates: Requirements 7.8, 7.9**

  - Commit: `feat: task 8 — ConnectionContractTests and LocalConnection/S3Connection contract subclasses`

- [~] 9. Checkpoint — ensure all new tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [~] 10. Update `__init__.py` — export new public API symbols
  - Add to `__all__`: `Connection`, `LocalConnection`, `S3Connection`, `WriteResult`,
    `OverwriteStatus`, `ConnectionContractTests`, `UnsupportedOperationError`,
    `TimeTravelError`, `ConflictError`, `ConfigurationError`, `DuplicateNameError`.
  - _Requirements: 1.1, 4.1, 11.1, 11.2, 11.3, 11.4, 11.5, 12.1_
  - Commit: `feat: task 10 — export new public API symbols from __init__.py`

- [~] 11. Migrate breaking change 1 — update `tests/conftest.py`
  - Replace `ctx.open_output("output.txt", "w")` in `simple_pipeline` with
    `ctx.open_output(LocalConnection("output.txt", base_output_dir=<output_dir>))`.
  - Ensure the fixture still works for all existing test files that depend on it.
  - _Requirements: 2.1, 5.3_
  - Commit: `feat: task 11 — migrate conftest.py simple_pipeline to LocalConnection`

- [~] 12. Migrate breaking change 1 — update `tests/test_context.py`
  - Replace all `ctx.open_input(path, mode)` and `ctx.open_output(filename)` calls with
    `LocalConnection`-wrapped equivalents.
  - Update assertions that check `str(expected) in ctx.outputs` to use descriptor field
    access (`ctx.outputs[i].connection_args["path"]` or similar).
  - _Requirements: 2.1, 5.1, 5.3_
  - Commit: `feat: task 12 — migrate test_context.py to LocalConnection`

- [~] 13. Migrate breaking changes 1 & 2 — update `tests/test_tracker.py`
  - Replace `ctx.open_input(path)` / `ctx.open_output(name)` in all pipeline lambdas with
    `LocalConnection`-wrapped equivalents.
  - Replace assertions on `record.input_paths` / `record.output_paths` with
    `record.inputs` / `record.outputs` descriptor access.
  - _Requirements: 2.1, 5.1, 5.3, 9.1, 9.2_
  - Commit: `feat: task 13 — migrate test_tracker.py to LocalConnection and descriptor API`

- [~] 14. Migrate breaking changes 1 & 2 — update `tests/test_replayer.py`
  - Replace `_track_simple_pipeline` and all inline `LineageRecord` constructions that use
    `input_paths` / `output_paths` with `inputs` / `outputs` descriptor lists.
  - Replace `ctx.open_input` / `ctx.open_output` plain-path calls with `LocalConnection`
    wrappers.
  - Update assertions that read `record.output_paths` to use `record.outputs`.
  - _Requirements: 2.1, 5.1, 5.3, 9.1, 9.2_
  - Commit: `feat: task 14 — migrate test_replayer.py to LocalConnection and descriptor API`

- [~] 15. Migrate breaking changes 1 & 2 — update `tests/test_integration.py`
  - Replace plain-path `ctx.open_input` / `ctx.open_output` calls with `LocalConnection`
    wrappers.
  - Replace `record.output_paths` / `replay_record.output_paths` access with descriptor
    iteration.
  - _Requirements: 2.1, 5.1, 5.3, 9.1, 9.2_
  - Commit: `feat: task 15 — migrate test_integration.py to LocalConnection and descriptor API`

- [~] 16. Migrate breaking changes 1 & 2 — update `tests/test_lineage_record.py` and `tests/test_lineage_store.py`
  - Replace the `lineage_record` Hypothesis strategy in both files to generate records
    with `InputDescriptor` / `OutputDescriptor` lists instead of `input_paths` /
    `output_paths` tuples.
  - _Requirements: 9.1, 9.2, 9.4, 9.5_
  - Commit: `feat: task 16 — migrate test_lineage_record.py and test_lineage_store.py to descriptor API`

- [~] 17. Migrate breaking changes 1 & 2 — update `demo.py`
  - Replace `ctx.open_input(input_path, "r")` with `ctx.open_input(LocalConnection(input_path))`.
  - Replace `ctx.open_output("summary.txt", "w")` and `ctx.open_output("copy.txt", "w")`
    with `LocalConnection`-wrapped equivalents.
  - Replace `record.output_paths` / `replay_record.output_paths` with descriptor access.
  - _Requirements: 2.1, 5.1, 5.3, 9.2_
  - Commit: `feat: task 17 — migrate demo.py to LocalConnection and descriptor API`

- [~] 18. Update `INTERFACES.md`
  - Update the `LineageRecord Fields` table to document `inputs` and `outputs` descriptor
    fields (remove `input_paths` / `output_paths`).
  - Update the JSON Schema section to show the new `inputs` / `outputs` array format.
  - Update `RunContext Methods` to show the new `Connection`-based signatures.
  - Add sections for `Connection`, `LocalConnection`, `S3Connection`, `WriteResult`,
    `OverwriteStatus`, `ConnectionContractTests`, and the five new exception types.
  - _Requirements: 4.3, 4.4, 4.5, 9.4_
  - Commit: `docs: task 18 — update INTERFACES.md for generalised-connections public API`

- [~] 19. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (Properties 1–9 from design)
- Unit tests validate specific examples, error conditions, and contract compliance
- Breaking changes are isolated to tasks 11–17 so they can be applied atomically after
  the new implementation is in place
