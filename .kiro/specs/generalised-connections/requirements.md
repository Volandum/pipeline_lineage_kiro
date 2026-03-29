# Requirements Document: generalised-connections

## Table of Contents

- [Introduction](#introduction)
- [Glossary](#glossary)
- [Requirements](#requirements)
  - [Requirement 1: Connection Abstraction](#requirement-1-connection-abstraction)
  - [Requirement 2: Local File Connection](#requirement-2-local-file-connection)
  - [Requirement 3: S3 Reference Connection](#requirement-3-s3-reference-connection)
  - [Requirement 4: User-Written Connectors](#requirement-4-user-written-connectors)
  - [Requirement 5: RunContext](#requirement-5-runcontext)
  - [Requirement 6: Named Inputs and Outputs](#requirement-6-named-inputs-and-outputs)
  - [Requirement 7: Conflict-Free Writes](#requirement-7-conflict-free-writes)
  - [Requirement 8: Time Travel for Replay](#requirement-8-time-travel-for-replay)
  - [Requirement 9: Lineage Record Generalisation](#requirement-9-lineage-record-generalisation)
  - [Requirement 10: Connection Serialisation and Reconstruction](#requirement-10-connection-serialisation-and-reconstruction)
  - [Requirement 11: New Exception Types](#requirement-11-new-exception-types)
  - [Requirement 12: Connector Contract Test Suite](#requirement-12-connector-contract-test-suite)

---

## Introduction

This feature generalises the connection model in `file_pipeline_lineage` beyond local files.
Currently, `RunContext` and `ReplayContext` assume all inputs and outputs are local filesystem
paths. This feature introduces a `Connection` abstraction that encapsulates how data is read
from and written to any backing store.

The package ships two built-in connectors: `LocalConnection` (fully supported) and
`S3Connection` (a reference/example implementation — not production-ready, clearly
documented as such). Users write their own connectors by subclassing `Connection`; there
is no registry or URI scheme resolution. `open_input` and `open_output` accept only
`Connection` objects — plain path strings are no longer accepted (breaking change).

The generalisation preserves all existing guarantees: per-run output isolation, conflict-free
writes, and full replay capability. Replay is extended to support time travel: each connection
type that supports it can seek to the state it held at the timestamp logged in the original
`LineageRecord`, so replays are reproducible even when the underlying data has since changed.

Each `Connection` implements only the I/O methods its backing store supports — `read`,
`atomic_read`, `write`, and `atomic_write` all default to raising `UnsupportedOperationError`.
No connector is required to implement all four.

---

## Glossary

- **Connection**: An abstract base class (ABC) with no abstract methods — a mixin/base
  class that connectors opt into. Defines four optional I/O methods (`read`, `atomic_read`,
  `write`, `atomic_write`) that all default to raising `UnsupportedOperationError`, plus a
  concrete `serialise` method and a `supports_time_travel` property.
- **Input_Connection**: A Connection used as a data source; opened via `ctx.open_input()`.
- **Output_Connection**: A Connection used as a data sink; opened via `ctx.open_output()`.
- **Connection_Name**: A string that uniquely identifies an input or output within a single
  run. Used as the identity key when matching recorded metadata during replay.
- **Time_Travel**: The ability of a Connection to seek to the state it held at a specific
  UTC timestamp, used during replay to reproduce the original input data. A Connection
  declares support via the `supports_time_travel` property.
- **Access_Timestamp**: The UTC timestamp recorded in the `LineageRecord` at the moment a
  Connection is opened for reading. Recorded unconditionally for all inputs as an audit
  trail of when data was accessed. Also used as the target for Time_Travel during replay
  when the Connection supports it.
- **Conflict_Free_Write**: A write operation guaranteed never to overwrite an existing
  output — enforced by incorporating the `run_id` into the output address. The default
  behaviour; can be explicitly overridden by passing `overwrite=True`.
- **WriteResult**: A value returned by `Connection.write()` or `Connection.atomic_write()`
  carrying `overwrite_status` — one of `OVERWRITE`, `NO_OVERWRITE`, `UNKNOWN`, or
  `IN_PROGRESS` — indicating whether the write actually overwrote an existing resource.
  `None` may be returned instead of a `WriteResult` when the connection cannot determine
  overwrite status; `RunContext` records `UNKNOWN` in that case. `IN_PROGRESS` is set on
  the output descriptor while a context-manager write is open and not yet committed.
- **Local_Connection**: The fully-supported built-in Connection backed by the local
  filesystem. Accepts a filesystem path as its constructor argument.
- **S3_Connection**: A reference/example Connection backed by AWS S3. Shipped as a
  starting point for users; not production-ready and clearly documented as such.
- **RunContext**: The existing I/O interception object, extended to accept Connection
  objects with an optional `name` argument. Plain path strings are no longer accepted.
- **ReplayContext**: The existing replay-time context, extended to reconstruct Connections
  from stored `LineageRecord` entries and apply Time_Travel where supported.
- **Lineage_Store**: Unchanged component; persists `LineageRecord` JSON files.
- **LineageRecord**: Restructured to store inputs and outputs as ordered lists of named
  descriptors. The old `input_paths`, `output_paths`, `input_refs`, `output_refs`,
  `input_timestamps`, and `time_travel_flags` fields are all removed. Breaking change.

---

## Requirements

### Requirement 1: Connection Abstraction

**User Story:** As a pipeline author, I want a uniform interface for all data sources and
sinks, so that I can write pipeline functions that work identically regardless of where
data lives.

#### Acceptance Criteria

1. THE Connection abstraction SHALL be an abstract base class (ABC) with NO abstract methods; it is a mixin/base class that connectors opt into. No connector is required to implement all methods.
2. THE Connection abstraction SHALL define `read(timestamp_utc: str | None = None)` as an optional method defaulting to raising `UnsupportedOperationError`. When implemented, it performs a streaming read and returns an object passed directly to user code (return type not prescribed). `timestamp_utc` is `None` for live reads and an ISO-8601 UTC string for time-travel reads.
3. THE Connection abstraction SHALL define `write(run_id: str, overwrite: bool = False)` as an optional method defaulting to raising `UnsupportedOperationError`. When implemented, it returns a context manager; `WriteResult | None` is available after `__exit__` completes. `run_id` is incorporated into the output address to guarantee Conflict_Free_Write semantics.
4. THE Connection abstraction SHALL define `atomic_read(timestamp_utc: str | None = None)` as an optional method defaulting to raising `UnsupportedOperationError`. When implemented, it reads and returns all data at once (return type not prescribed).
5. THE Connection abstraction SHALL define `atomic_write(data, run_id: str, overwrite: bool = False)` as an optional method defaulting to raising `UnsupportedOperationError`. When implemented, it writes data atomically and returns `WriteResult | None`. `None` means the connection cannot determine overwrite status.
6. THE Connection abstraction SHALL provide a concrete `serialise() -> dict` implementation that uses `inspect.signature(self.__init__)` to return a dict of `{param_name: getattr(self, param_name)}` for each `__init__` parameter. Subclasses MAY override `serialise()` when the default is incorrect (e.g. to exclude secrets or rename fields).
7. THE Connection abstraction SHALL define a `supports_time_travel` property returning `bool`; implementations that do not support time travel SHALL return `False` (the default).
8. THE `serialise` method SHALL NOT include secrets (e.g. credentials, tokens) in the returned dict; secrets MUST NOT be stored as instance attributes and MUST be sourced from the environment by the Connection's `__init__` at reconstruction time.
9. WHEN `ctx.open_input(connection)` is called with a Connection object, THE RunContext SHALL use that Connection object directly.
10. WHEN `ctx.open_output(connection)` is called with a Connection object, THE RunContext SHALL use that Connection object directly.

---

### Requirement 2: Local File Connection

**User Story:** As a pipeline author, I want a built-in Connection type for local files,
so that I can use the lineage system with filesystem-based pipelines.

#### Acceptance Criteria

1. THE Local_Connection SHALL accept a plain filesystem path as its constructor argument.
2. WHEN `Local_Connection.read(timestamp_utc=None)` is called, THE Local_Connection SHALL open the file at the recorded path for reading and return a readable file-like object.
3. WHEN `Local_Connection.write(run_id, overwrite=False)` is called, THE Local_Connection SHALL return a context manager. On `__enter__`: if `overwrite=False`, check for conflict and raise `ConflictError` if the output path exists; open the file and set the output descriptor to `IN_PROGRESS`. On `__exit__` (success): close the file and update the descriptor to `NO_OVERWRITE` or `OVERWRITE`. On `__exit__` (exception): close/remove the partial file; the descriptor remains `IN_PROGRESS`.
4. THE Local_Connection SHALL NOT implement `atomic_read` or `atomic_write`; calling either SHALL raise `UnsupportedOperationError`.
5. WHEN `Local_Connection.read` is called with a non-`None` `timestamp_utc`, THE Local_Connection SHALL raise a descriptive `UnsupportedOperationError` because local files do not support Time_Travel.
6. `Local_Connection.serialise()` SHALL return `{"path": "<absolute path string>"}`.

---

### Requirement 3: S3 Reference Connection

**User Story:** As a pipeline author, I want a reference S3 Connection implementation to
use as a starting point, so that I can understand how to implement a cloud-storage
connector and adapt it for production use.

> **Note**: `S3Connection` is a reference/example implementation only. It is not
> production-ready and is clearly documented as such in the package.

#### Acceptance Criteria

1. THE S3_Connection SHALL accept `bucket`, `key`, and `time_travel: bool = False` as constructor arguments. `time_travel=True` declares that the bucket has S3 Object Versioning enabled and time-travel reads are supported.
2. WHEN `S3_Connection.read(timestamp_utc=None)` is called, THE S3_Connection SHALL download the object at the recorded S3 location and return a readable file-like object (streaming via download).
3. WHEN `S3_Connection.read(timestamp_utc)` is called with a non-`None` `timestamp_utc`, THE S3_Connection SHALL retrieve the S3 object version whose `LastModified` is the latest at or before `timestamp_utc`, enabling Time_Travel.
4. IF no S3 object version exists at or before the requested `timestamp_utc`, THEN THE S3_Connection SHALL raise a descriptive `TimeTravelError` identifying the bucket/key and the requested timestamp.
5. WHEN `S3_Connection.atomic_write(data, run_id, overwrite=False)` is called, THE S3_Connection SHALL upload `data` to a key derived by inserting `<run_id>/` as a prefix segment before the original key's filename, using a single PUT. It SHALL return a `WriteResult` with `OVERWRITE` or `NO_OVERWRITE` based on whether the key existed before upload.
6. THE S3_Connection SHALL NOT implement `write` (streaming context manager); calling it SHALL raise `UnsupportedOperationError`.
7. THE S3_Connection SHALL NOT implement `atomic_read`; calling it SHALL raise `UnsupportedOperationError`.
8. THE S3_Connection SHALL use S3 Object Versioning to support Time_Travel; IF versioning is not enabled on the bucket, THEN THE S3_Connection SHALL raise a descriptive `ConfigurationError` when `read` is called with a non-`None` `timestamp_utc`.
9. `S3_Connection.serialise()` SHALL return `{"bucket": "<bucket>", "key": "<key>", "time_travel": <bool>}` and SHALL NOT include AWS credentials.
10. `S3_Connection.supports_time_travel` SHALL return the value of the `time_travel` constructor argument.

---

### Requirement 4: User-Written Connectors

**User Story:** As a pipeline author, I want to implement my own Connection types, so that
I can connect to any data store without modifying core library code.

#### Acceptance Criteria

1. THE Connection ABC SHALL be importable from the package's public API so that users can subclass it directly.
2. WHEN a user-supplied Connection instance is passed to `ctx.open_input()` or `ctx.open_output()`, THE RunContext SHALL use it identically to a built-in Connection type.
3. THE package documentation SHALL clearly state that `LocalConnection` is the only fully-supported built-in connector and that `S3Connection` is a reference implementation only.
4. THE package documentation SHALL clearly state that no method of `Connection` is required — connectors implement only the methods their backing store supports, and unimplemented methods raise `UnsupportedOperationError` by default.
5. THE package documentation SHALL provide a worked example showing how to implement a custom Connection subclass, including a `PostgresConnection` documentation example (not shipped as code) demonstrating `atomic_read`, `atomic_write`, and a streaming `write` context manager using a database transaction.
6. IF a user-written Connection does not support Time_Travel and the Replayer requests a time-travel read, THEN THE ReplayContext SHALL raise a descriptive `UnsupportedOperationError` identifying the Connection_Name and the requested timestamp.

---

### Requirement 5: RunContext

**User Story:** As a pipeline author, I want `RunContext` to accept Connection objects
for inputs and outputs, so that I can use any Connection type in my pipeline functions.

#### Acceptance Criteria

1. THE RunContext SHALL accept `ctx.open_input(connection, name=None)` where `connection` MUST be a Connection object; calls `connection.read(None)`.
2. THE RunContext SHALL accept `ctx.atomic_read(connection, name=None)` where `connection` MUST be a Connection object; calls `connection.atomic_read(None)`.
3. THE RunContext SHALL accept `ctx.open_output(connection, name=None, overwrite=False)` where `connection` MUST be a Connection object; calls `connection.write(run_id, overwrite)` and returns the context manager to the caller.
4. THE RunContext SHALL accept `ctx.atomic_write(connection, data, name=None, overwrite=False)` where `connection` MUST be a Connection object; calls `connection.atomic_write(data, run_id, overwrite)`.
5. WHEN `ctx.open_input(connection)` is called, THE RunContext SHALL call `connection.read(timestamp_utc=None)`, record the input descriptor, and return the resulting object.
6. WHEN `ctx.atomic_read(connection)` is called, THE RunContext SHALL call `connection.atomic_read(timestamp_utc=None)`, record the input descriptor, and return the result.
7. WHEN `ctx.open_output(connection)` is called, THE RunContext SHALL call `connection.write(run_id=ctx.run_id, overwrite=overwrite)`, immediately save the output descriptor with `overwrite_status: IN_PROGRESS`, and return the context manager to the caller.
8. WHEN `ctx.atomic_write(connection, data)` is called, THE RunContext SHALL call `connection.atomic_write(data, run_id=ctx.run_id, overwrite=overwrite)`, record the output descriptor with the returned `WriteResult | None`, and record `UNKNOWN` if `None` is returned.
9. THE RunContext SHALL record the Access_Timestamp (ISO-8601 UTC) at the moment each `ctx.open_input()` or `ctx.atomic_read()` call is made and store it in the input descriptor.

---

### Requirement 6: Named Inputs and Outputs

**User Story:** As a pipeline author, I want to assign names to inputs and outputs, so
that the lineage record can unambiguously identify each connection during replay.

#### Acceptance Criteria

1. WHEN `ctx.open_input(connection, name=None)` is called without a `name`, THE RunContext SHALL auto-generate a Connection_Name in the format `<index>:<ClassName>(<truncated_params>)` where `<index>` is the 1-based position of this input, `<ClassName>` is the connection's class name, and `<truncated_params>` is a truncated `key=value` representation of `connection.serialise()`, truncated to at most 50 characters with a trailing `...` if truncated.
2. WHEN `ctx.open_output(connection, name=None)` is called without a `name`, THE RunContext SHALL auto-generate a Connection_Name using the same scheme, with the index being the 1-based position of this output.
3. IF `ctx.open_input` or `ctx.open_output` is called with a `name` that is already in use within the same run, THEN THE RunContext SHALL immediately raise a `DuplicateNameError` without opening the resource or recording any descriptor.
4. THE Connection_Name SHALL be the identity key used to match inputs and outputs to their recorded metadata during replay.

---

### Requirement 7: Conflict-Free Writes

**User Story:** As a data engineer, I want write operations to be conflict-free by default,
but optionally permit explicit overwrites with full audit trail, so that run isolation is
the safe default while still allowing intentional overwrites when needed.

#### Acceptance Criteria

1. THE Connection abstraction SHALL define `write(run_id: str, overwrite: bool = False)` as an optional method that returns a context manager; `WriteResult | None` is available after `__exit__` completes. `None` means the connection cannot determine overwrite status.
2. THE Connection abstraction SHALL define `atomic_write(data, run_id: str, overwrite: bool = False)` as an optional method that writes atomically and returns `WriteResult | None`.
3. WHEN `overwrite=False` (the default), THE Connection SHOULD raise `ConflictError` if the derived output address already exists, before opening the resource.
4. WHEN `overwrite=True`, THE Connection SHALL proceed without a conflict check and return a `WriteResult` indicating whether an overwrite actually occurred (`OVERWRITE`), did not occur (`NO_OVERWRITE`), or could not be determined (`UNKNOWN`).
5. THE RunContext SHALL expose `ctx.open_output(connection, name=None, overwrite=False)` and pass `overwrite` through to `connection.write()`.
6. THE RunContext SHALL expose `ctx.atomic_write(connection, data, name=None, overwrite=False)` and pass `overwrite` through to `connection.atomic_write()`.
7. THE RunContext SHALL pass `ctx.run_id` to every `connection.write()` and `connection.atomic_write()` call.
8. WHEN `ctx.open_output` is called, THE Tracker SHALL immediately save the `LineageRecord` with `overwrite_status: "in_progress"` on the output descriptor. WHEN the context manager's `__exit__` fires successfully, THE Tracker SHALL update the descriptor to `"overwrite"` or `"no_overwrite"`. IF `__exit__` never fires (e.g. crash), `"in_progress"` remains in the stored record.
9. THE LineageRecord output descriptor SHALL record `overwrite_requested: bool` and `overwrite_status: "overwrite" | "no_overwrite" | "unknown" | "in_progress"`.
10. User-written Connection implementations are responsible for honouring the `overwrite` flag and raising `ConflictError` appropriately when `overwrite=False`.

---

### Requirement 8: Time Travel for Replay

**User Story:** As a data engineer, I want replays to reproduce the original input data
as it existed at the time of the original run where possible, falling back gracefully
for connections that do not support time travel.

#### Acceptance Criteria

1. WHEN the Replayer constructs a `ReplayContext`, THE ReplayContext SHALL check `connection.supports_time_travel` for each input before passing the recorded `Access_Timestamp`.
2. WHEN `connection.supports_time_travel` is `True`, THE ReplayContext SHALL call `connection.read(timestamp_utc)` with the recorded `Access_Timestamp` for that input.
3. WHEN `connection.supports_time_travel` is `False`, THE ReplayContext SHALL call `connection.read(None)` (live read) and record `time_travel: false` in the replay `LineageRecord`.
4. THE Replayer SHALL record in the replay `LineageRecord` whether each input was read via time travel (`time_travel: true`) or via direct live access (`time_travel: false`).

---

### Requirement 9: Lineage Record Generalisation

**User Story:** As a data engineer, I want the `LineageRecord` to capture named connection
descriptors for all inputs and outputs, so that the lineage store is a complete audit
trail and supports accurate replay regardless of connection type.

> **Breaking change**: `input_paths`, `output_paths`, `input_refs`, `output_refs`,
> `input_timestamps`, and `time_travel_flags` are all removed and replaced by `inputs`
> and `outputs` as ordered lists of named descriptors.

#### Acceptance Criteria

1. THE LineageRecord SHALL store `inputs` as a list of input descriptors, each containing `name` (str), `connection_class` (str), `connection_args` (dict), `access_timestamp` (ISO-8601 UTC str), and `time_travel` (bool). The `name` field is the identity key; no positional semantics are implied.
2. THE LineageRecord SHALL store `outputs` as a list of output descriptors, each containing `name` (str), `connection_class` (str), `connection_args` (dict), `overwrite_requested` (bool), and `overwrite_status` (`"overwrite"` | `"no_overwrite"` | `"unknown"` | `"in_progress"`). The `name` field is the identity key; no positional semantics are implied.
3. THE `connection_class` field SHALL be the fully-qualified import path of the Connection class, e.g. `"mypackage.connectors:S3Connection"`.
4. WHEN a `LineageRecord` is serialised to JSON, THE LineageRecord SHALL represent `inputs` and `outputs` as JSON arrays of objects.
5. FOR ALL valid `LineageRecord` objects, serialising to JSON and then deserialising SHALL produce an equal object (round-trip property).

---

### Requirement 10: Connection Serialisation and Reconstruction

**User Story:** As a data engineer, I want Connections to be reconstructable from stored
`LineageRecord` entries, so that the Replayer can recreate the exact connection used in
the original run without any additional configuration.

#### Acceptance Criteria

1. THE Replayer SHALL reconstruct a Connection from a stored descriptor by using `importlib` to load the class identified by `connection_class`, then calling `cls(**connection_args)`.
2. THE Connection's `__init__` SHALL source any required secrets from the environment at reconstruction time; secrets SHALL NOT be present in `connection_args`.
3. FOR ALL Connection types, calling `cls(**connection.serialise())` SHALL produce a Connection that behaves equivalently to the original for the purposes of `read` and `write` (round-trip property).
4. WHEN `importlib` cannot locate the class identified by `connection_class`, THE Replayer SHALL raise a descriptive `ConfigurationError` identifying the missing class.
5. WHEN `cls(**connection_args)` raises an exception due to missing or invalid arguments, THE Replayer SHALL raise a descriptive `ConfigurationError` identifying the Connection_Name and the cause.

---

### Requirement 11: New Exception Types

**User Story:** As a pipeline author, I want descriptive, typed exceptions for connection
failures, so that I can handle specific error conditions programmatically.

#### Acceptance Criteria

1. THE `exceptions` module SHALL define `UnsupportedOperationError` as a subclass of `LineageError`, raised when a Connection is asked to perform an operation it does not support (e.g. Time_Travel on a Local_Connection).
2. THE `exceptions` module SHALL define `TimeTravelError` as a subclass of `LineageError`, raised when a time-travel read cannot be satisfied (e.g. no S3 version exists at or before the requested timestamp).
3. THE `exceptions` module SHALL define `ConflictError` as a subclass of `LineageError`, raised when a Conflict_Free_Write would produce an output address that already exists.
4. THE `exceptions` module SHALL define `ConfigurationError` as a subclass of `LineageError`, raised when a Connection is misconfigured or cannot be reconstructed.
5. THE `exceptions` module SHALL define `DuplicateNameError` as a subclass of `LineageError`, raised when `open_input` or `open_output` is called with a name already in use within the same run.
6. All five new exception classes SHALL be added to the existing `src/file_pipeline_lineage/exceptions.py`, alongside `LineageError`, `RunNotFoundError`, `MissingInputError`, and `MissingCommitError`.

---

### Requirement 12: Connector Contract Test Suite

**User Story:** As a connector author, I want a reusable test suite that verifies my
Connection implementation satisfies the connector contract, so that I can be confident
my connector will work correctly with the lineage framework.

#### Acceptance Criteria

1. THE package SHALL ship a `ConnectionContractTests` base class (importable from the public API) that users subclass in their own test suite to verify a Connection implementation.
2. THE `ConnectionContractTests` class SHALL define an abstract `make_connection() -> Connection` method that subclasses implement to supply the Connection under test.
3. THE contract test suite SHALL verify that `serialise()` returns a JSON-serialisable dict.
4. THE contract test suite SHALL verify that `cls(**connection.serialise())` reconstructs a Connection whose `serialise()` output equals the original (round-trip property).
5. THE contract test suite SHALL verify that `supports_time_travel` returns a `bool`.
6. THE contract test suite SHALL be capability-aware: each I/O method (`read`, `atomic_read`, `write`, `atomic_write`) is only tested if the connection does not raise `UnsupportedOperationError` when called. Connections that do not implement a method are not penalised for it.
7. WHEN `read(None)` is supported, THE contract test suite SHALL verify it returns a readable object.
8. WHEN `write(run_id)` is supported, THE contract test suite SHALL verify the context manager completes and the output descriptor is updated to a final `overwrite_status` (not `IN_PROGRESS`).
9. WHEN `atomic_write(data, run_id)` is supported, THE contract test suite SHALL verify it returns `WriteResult | None` with a valid `overwrite_status` when not `None`.
10. THE contract test suite SHALL check whether two distinct `run_id` values produce non-overlapping output addresses (for any write method the connection supports), and SHALL emit a clear warning or test note if the connection returns output addresses that cannot be compared (e.g. opaque objects), so the user can determine for themselves whether isolation is satisfied.
11. THE package's own tests for `LocalConnection` SHALL subclass `ConnectionContractTests`, serving as the reference demo of correct usage.
12. THE package's own tests for `S3Connection` SHALL also subclass `ConnectionContractTests`, demonstrating contract compliance for the reference S3 implementation.
