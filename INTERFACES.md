# INTERFACES.md

## Table of Contents

- [Overview](#overview)
- [Pipeline Function Contract](#pipeline-function-contract)
  - [Required behaviour](#required-behaviour)
  - [Replay constraints](#replay-constraints)
- [Data Models](#data-models)
  - [LineageRecord Fields](#lineagerecord-fields)
  - [InputDescriptor Fields](#inputdescriptor-fields)
  - [OutputDescriptor Fields](#outputdescriptor-fields)
- [JSON Schema](#json-schema)
  - [JSON Schema — inputs and outputs](#json-schema--inputs-and-outputs)
- [Public API — Connection](#public-api--connection)
  - [Connection ABC](#connection-abc)
  - [Connection ABC — method reference](#connection-abc--method-reference)
  - [LocalConnection](#localconnection)
  - [S3Connection](#s3connection)
  - [WriteResult and OverwriteStatus](#writeresult-and-overwritestatus)
  - [ConnectionContractTests](#connectioncontracttests)
- [Public API — RunContext](#public-api--runcontext)
  - [RunContext Constructor and Properties](#runcontext-constructor-and-properties)
  - [RunContext Methods](#runcontext-methods)
- [Public API — ReplayContext](#public-api--replaycontext)
  - [ReplayContext — time-travel routing](#replaycontext--time-travel-routing)
- [Public API — LineageStore](#public-api--lineagestore)
- [Public API — Tracker](#public-api--tracker)
- [Public API — Replayer](#public-api--replayer)
- [Exceptions](#exceptions)
- [Disk Layout](#disk-layout)
---

## Overview

`file_pipeline_lineage` wraps file-based data pipeline functions to capture full lineage:
the git commit and importable reference of the code that ran, the connections consumed,
the connections produced, and enough metadata to replay any past run exactly.

All public names are importable directly from `file_pipeline_lineage`:

```python
from file_pipeline_lineage import (
    RunContext, ReplayContext, LineageRecord, LineageStore,
    Tracker, Replayer,
    Connection, LocalConnection, S3Connection,
    WriteResult, OverwriteStatus,
    ConnectionContractTests,
    LineageError, RunNotFoundError, MissingInputError, MissingCommitError,
    UnsupportedOperationError, TimeTravelError,
    ConflictError, ConfigurationError, DuplicateNameError,
)
```

---

## Pipeline Function Contract

A pipeline function must accept a single `RunContext` argument and return `None`.

```python
def my_pipeline(ctx: RunContext) -> None:
    with ctx.open_input(LocalConnection("data/input.csv")) as f:
        data = f.read()
    with ctx.open_output(LocalConnection("result.csv")) as f:
        f.write(data)
```

### Required behaviour

| Requirement | Detail |
|---|---|
| Signature | `(ctx: RunContext) -> None` |
| All reads | Must use `ctx.open_input()` or `ctx.atomic_read()` — plain `open()` reads are invisible to lineage capture |
| All writes | Must use `ctx.open_output()` or `ctx.atomic_write()` — plain `open()` writes are not recorded and not isolated per run |
| Exceptions | Any exception propagates; a `failed` record capturing partial outputs is saved before re-raise |

### Replay constraints

For a pipeline to be replayable, it must satisfy these additional constraints:

| Constraint | Detail |
|---|---|
| Module-level definition | The function must be defined at module level — closures and lambdas cannot be imported by `function_ref` |
| Committed to git | The module containing the function must be committed to the git repository at the time `track()` is called |
| Importable by reference | `function_ref` is `"module:qualname"` — the module must be importable from the repo root |
| Deterministic (recommended) | For replay outputs to match originals, the function should produce the same output given the same inputs |

Violating any replay constraint will cause `Replayer.replay()` to fail or produce incorrect results.

---

## Data Models

### LineageRecord Fields

`LineageRecord` is a frozen dataclass. All fields are set at construction time and are immutable.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | UUID4 string assigned by `Tracker` or `Replayer` |
| `timestamp_utc` | `str` | ISO-8601 UTC timestamp, e.g. `2024-01-15T10:30:00.123456+00:00` |
| `function_name` | `str` | `fn.__name__` of the pipeline function |
| `git_commit` | `str` | Full 40-char SHA of `HEAD` at the time `track()` was called |
| `function_ref` | `str` | Importable reference: `"module:qualname"`, e.g. `"mypkg.pipelines:transform"` |
| `inputs` | `tuple[InputDescriptor, ...]` | Ordered list of input connection descriptors |
| `outputs` | `tuple[OutputDescriptor, ...]` | Ordered list of output connection descriptors |
| `status` | `str` | `"success"` or `"failed"` |
| `exception_message` | `str \| None` | `None` on success; exception string on failure |
| `original_run_id` | `str \| None` | `None` for original runs; the replayed `run_id` for replay runs |

### InputDescriptor Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Identity key, e.g. `"1:LocalConnection(path=/data/in.csv)"` |
| `connection_class` | `str` | Fully-qualified import path, e.g. `"file_pipeline_lineage.connections:LocalConnection"` |
| `connection_args` | `dict` | Result of `connection.serialise()` — JSON-primitive values only |
| `access_timestamp` | `str` | ISO-8601 UTC recorded at the moment `open_input` / `atomic_read` was called |
| `time_travel` | `bool` | `False` for original runs; `True` if replay used time-travel read |

### OutputDescriptor Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Identity key, e.g. `"1:LocalConnection(path=/data/out.csv)"` |
| `connection_class` | `str` | Fully-qualified import path |
| `connection_args` | `dict` | Result of `connection.serialise()` |
| `overwrite_requested` | `bool` | Whether `overwrite=True` was passed to `open_output` / `atomic_write` |
| `overwrite_status` | `str` | `"overwrite"` \| `"no_overwrite"` \| `"unknown"` \| `"in_progress"` |

---

## JSON Schema

Each record is stored as a single JSON file. All fields are present; nullable fields use JSON `null`.

```json
{
  "run_id": "<uuid4>",
  "timestamp_utc": "<iso8601-utc>",
  "function_name": "<str>",
  "git_commit": "<40-char-hex>",
  "function_ref": "<module>:<qualname>",
  "inputs": [ ... ],
  "outputs": [ ... ],
  "status": "success | failed",
  "exception_message": "<str> | null",
  "original_run_id": "<uuid4> | null"
}
```

Use `LineageRecord.to_dict()` / `LineageRecord.from_dict()` for round-trip serialisation.
`connection_args` values must be JSON-primitive (str, int, float, bool, None). The `name`
field is the identity key; array order reflects call order at runtime.

### JSON Schema — inputs and outputs

```json
"inputs": [
  {
    "name": "1:LocalConnection(path=/data/in.csv)",
    "connection_class": "file_pipeline_lineage.connections:LocalConnection",
    "connection_args": {"path": "/data/in.csv"},
    "access_timestamp": "2024-01-15T10:30:00.000000+00:00",
    "time_travel": false
  }
],
"outputs": [
  {
    "name": "1:LocalConnection(path=/data/out.csv)",
    "connection_class": "file_pipeline_lineage.connections:LocalConnection",
    "connection_args": {"path": "/data/out.csv"},
    "overwrite_requested": false,
    "overwrite_status": "no_overwrite"
  }
]
```

During an active `open_output` context manager, `overwrite_status` is `"in_progress"`.
On successful `__exit__` it updates to `"no_overwrite"` or `"overwrite"`. A crashed run
leaves `"in_progress"` in the stored file — a useful debugging signal.

---

## Public API — Connection

### Connection ABC

`Connection` is an abstract base class with **no abstract methods** — connectors opt in by
subclassing and implementing only the methods their backing store supports. Unimplemented
methods raise `UnsupportedOperationError` by default.

```python
class Connection(ABC):
    def read(self, timestamp_utc: str | None = None): ...
    def atomic_read(self, timestamp_utc: str | None = None): ...
    def write(self, run_id: str, overwrite: bool = False): ...
    def atomic_write(self, data, run_id: str, overwrite: bool = False): ...
    def serialise(self) -> dict: ...
    @property
    def supports_time_travel(self) -> bool: ...
```

### Connection ABC — method reference

| Method / Property | Description |
|---|---|
| `read(timestamp_utc=None)` | Streaming read. `None` → live read; ISO-8601 UTC string → time-travel read. Return type not prescribed. |
| `atomic_read(timestamp_utc=None)` | Read and return all data at once. Return type not prescribed. |
| `write(run_id, overwrite=False)` | Returns a context manager. `WriteResult \| None` available on the context manager after `__exit__`. |
| `atomic_write(data, run_id, overwrite=False)` | Write atomically. Returns `WriteResult \| None`. `None` means overwrite status cannot be determined. |
| `serialise()` | Returns a JSON-serialisable `dict` of non-secret constructor args. Default uses `inspect.signature`; override to exclude secrets. |
| `supports_time_travel` | `bool`. `False` by default; override to `True` if the backing store supports versioned reads. |

Secrets (credentials, tokens) must **not** be stored as instance attributes and must **not**
appear in `serialise()` output. Source them from the environment in `__init__` at
reconstruction time.

---

### LocalConnection

`LocalConnection` is the fully-supported built-in connector for local filesystem paths.
It implements `read` and `write`; `atomic_read` and `atomic_write` raise
`UnsupportedOperationError`.

```python
class LocalConnection(Connection):
    def __init__(self, path: str | Path, base_output_dir: str | Path | None = None) -> None: ...
    def read(self, timestamp_utc: str | None = None) -> IO: ...
    def write(self, run_id: str, overwrite: bool = False) -> ContextManager[IO]: ...
    def serialise(self) -> dict: ...  # {"path": "<absolute path>"}
    @property
    def supports_time_travel(self) -> bool: ...  # always False
```

| Behaviour | Detail |
|---|---|
| `read(None)` | Opens `path` for reading; returns a readable file-like object |
| `read(timestamp_utc)` | Raises `UnsupportedOperationError` — local files do not support time travel |
| `write(run_id)` | Returns a context manager writing to `<base_output_dir>/<run_id>/<filename>` |
| `write` `__enter__` | Raises `ConflictError` if output path exists and `overwrite=False` |
| `write` `__exit__` (success) | Closes file; `ctx_mgr.result` is set to `WriteResult(NO_OVERWRITE \| OVERWRITE)` |
| `write` `__exit__` (exception) | Closes and removes partial file; `ctx_mgr.result` remains `None` |
| `serialise()` | Returns `{"path": "<absolute path string>"}` |

`base_output_dir` is injected by `RunContext` when not set; it is not included in
`serialise()` output (runtime concern, not connection identity).

---

### S3Connection

`S3Connection` is a **reference/example** S3 connector — not production-ready. It
implements `read` (streaming download with optional time travel) and `atomic_write`
(single PUT). `write` and `atomic_read` raise `UnsupportedOperationError`. Requires
`boto3` (optional dependency, imported lazily).

```python
class S3Connection(Connection):
    def __init__(self, bucket: str, key: str, time_travel: bool = False) -> None: ...
    def read(self, timestamp_utc: str | None = None) -> IO: ...
    def atomic_write(self, data, run_id: str, overwrite: bool = False) -> WriteResult: ...
    def serialise(self) -> dict: ...  # {"bucket": ..., "key": ..., "time_travel": bool}
    @property
    def supports_time_travel(self) -> bool: ...  # returns self.time_travel
```

| Behaviour | Detail |
|---|---|
| `read(None)` | Streaming download of the current object; returns `BytesIO` |
| `read(timestamp_utc)` | Time-travel via S3 Object Versioning; raises `TimeTravelError` if no version found |
| `read` with versioning disabled | Raises `ConfigurationError` identifying the bucket |
| `atomic_write(data, run_id)` | Single PUT to `<run_id>/<key_filename>`; returns `WriteResult(OVERWRITE \| NO_OVERWRITE)` |
| `serialise()` | Returns `{"bucket": "...", "key": "...", "time_travel": bool}` — no credentials |

AWS credentials are sourced from the environment by `boto3` at call time and are never
stored as instance attributes.

---

### WriteResult and OverwriteStatus

```python
class OverwriteStatus(str, Enum):
    OVERWRITE    = "overwrite"
    NO_OVERWRITE = "no_overwrite"
    UNKNOWN      = "unknown"
    IN_PROGRESS  = "in_progress"

@dataclass(frozen=True)
class WriteResult:
    overwrite_status: OverwriteStatus
```

`OverwriteStatus` values serialise to lowercase strings for JSON compatibility.
`IN_PROGRESS` is set on the output descriptor immediately when `ctx.open_output` is called
and updated to a final status when `__exit__` fires successfully. If the process crashes
before `__exit__`, `"in_progress"` remains in the stored record — a useful debugging signal.

`write()` and `atomic_write()` return `WriteResult | None`. `None` means the connection
cannot determine overwrite status; `RunContext` records `UNKNOWN` in that case.

---

### ConnectionContractTests

`ConnectionContractTests` is a reusable `pytest` base class for verifying that a
`Connection` implementation satisfies the connector contract. Subclass it and implement
`make_connection()` to run all contract checks against your connector.

```python
class ConnectionContractTests:
    @abstractmethod
    def make_connection(self) -> Connection: ...
```

Each test method is capability-aware: it is automatically skipped when the connection
raises `UnsupportedOperationError` for the method under test.

| Contract test | Verifies |
|---|---|
| `test_serialise_returns_json_serialisable_dict` | `serialise()` returns a JSON-serialisable `dict` |
| `test_round_trip_serialise` | `cls(**conn.serialise()).serialise() == conn.serialise()` |
| `test_supports_time_travel_returns_bool` | `supports_time_travel` returns a `bool` |
| `test_read_returns_readable_object` | `read(None)` returns a non-`None` object (if supported) |
| `test_write_context_manager_completes_with_final_status` | `write(run_id)` context manager completes; `overwrite_status` is not `IN_PROGRESS` (if supported) |
| `test_atomic_write_returns_valid_result` | `atomic_write(data, run_id)` returns `WriteResult \| None` with valid status (if supported) |
| `test_distinct_run_ids_produce_non_overlapping_addresses` | Two distinct `run_id` values produce non-overlapping output addresses (if supported) |

---

## Public API — RunContext

### RunContext Constructor and Properties

```python
class RunContext:
    def __init__(self, run_id: str, base_output_dir: str | Path | None = None) -> None: ...
```

| Parameter | Type | Description |
|---|---|---|
| `run_id` | `str` | Identifier for this run (UUID4 assigned by `Tracker`) |
| `base_output_dir` | `str \| Path \| None` | Root directory under which `LocalConnection` output files are written; defaults to `"."` |

| Property | Type | Description |
|---|---|---|
| `run_id` | `str` | The run identifier passed at construction |
| `inputs` | `tuple[InputDescriptor, ...]` | Immutable snapshot of all input descriptors recorded so far |
| `outputs` | `tuple[OutputDescriptor, ...]` | Immutable snapshot of all output descriptors recorded so far |

### RunContext Methods

```python
def open_input(self, connection: Connection, name: str | None = None): ...
def atomic_read(self, connection: Connection, name: str | None = None): ...
def open_output(self, connection: Connection, name: str | None = None, overwrite: bool = False): ...
def atomic_write(self, connection: Connection, data, name: str | None = None, overwrite: bool = False): ...
```

| Method | Calls on connection | Returns | Descriptor timing |
|---|---|---|---|
| `open_input` | `conn.read(None)` | result object | recorded at call time with `access_timestamp` |
| `atomic_read` | `conn.atomic_read(None)` | result object | recorded at call time with `access_timestamp` |
| `open_output` | `conn.write(run_id, overwrite)` | context manager | saved as `IN_PROGRESS` immediately; updated on `__exit__` success |
| `atomic_write` | `conn.atomic_write(data, run_id, overwrite)` | `WriteResult \| None` | recorded after call; `None` → `UNKNOWN` |

Auto-name format (when `name=None`): `<1-based-index>:<ClassName>(<truncated_params>)`.
The params portion is truncated to at most 50 characters with a trailing `...` if truncated.
Raises `DuplicateNameError` immediately if `name` is already in use within the same run.

---

## Public API — ReplayContext

`ReplayContext` is a subclass of `RunContext`. The constructor and `open_input` /
`atomic_read` differ; `open_output` and `atomic_write` are inherited unchanged.

```python
class ReplayContext(RunContext):
    def __init__(
        self,
        run_id: str,
        orig_run_id: str,
        replay_root: str | Path,
        original_inputs: dict[str, InputDescriptor] | None = None,
    ) -> None: ...
```

| Parameter | Description |
|---|---|
| `run_id` | UUID4 for this replay run |
| `orig_run_id` | `run_id` of the original run being replayed |
| `replay_root` | Root directory for all replay outputs |
| `original_inputs` | Map of `name → InputDescriptor` from the original `LineageRecord`; used for time-travel routing |

### ReplayContext — time-travel routing

`open_input` and `atomic_read` apply time-travel routing per input:

- If `connection.supports_time_travel` is `True`: calls `connection.read(access_timestamp)`
  and records `time_travel: true` in the replay descriptor.
- If `connection.supports_time_travel` is `False`: calls `connection.read(None)` (live read)
  and records `time_travel: false`.

Output path structure: `<replay_root>/<orig_run_id>/<replay_run_id>/<filename>`, ensuring
replay outputs are fully isolated from both the original run and other replays.

---

## Public API — LineageStore

```python
class LineageStore:
    def __init__(self, store_root: str | Path) -> None: ...
    def save(self, record: LineageRecord) -> Path: ...
    def load(self, run_id: str) -> LineageRecord: ...
    def list_run_ids(self) -> list[str]: ...
```

| Method | Returns | Description |
|---|---|---|
| `__init__` | — | Creates `store_root` directory if absent |
| `save(record)` | `Path` | Atomically writes `<store_root>/<run_id>.json`; returns the path written |
| `load(run_id)` | `LineageRecord` | Deserialises record; raises `RunNotFoundError` if absent, `LineageError` on corrupt JSON |
| `list_run_ids()` | `list[str]` | Returns all stored run IDs sorted by filename |

`save` uses a write-to-temp-then-`os.replace` pattern for atomicity.

---

## Public API — Tracker

```python
class Tracker:
    def __init__(self, store: LineageStore) -> None: ...
    def track(
        self,
        fn: Callable[[RunContext], None],
        base_output_dir: str | Path,
    ) -> LineageRecord: ...
```

`track` assigns a UUID4 `run_id`, captures `git rev-parse HEAD`, constructs a `RunContext`,
calls `fn(ctx)`, then saves and returns a `LineageRecord`.

On exception: saves a `failed` record with outputs captured at exception time, then re-raises.
Raises `LineageError` if called outside a git repository or with no commits.

---

## Public API — Replayer

```python
class Replayer:
    def __init__(self, store: LineageStore, replay_root: str | Path) -> None: ...
    def replay(self, run_id: str) -> LineageRecord: ...
```

`replay` loads the original record, reconstructs each `Connection` from its stored
descriptor via `importlib` (`cls(**connection_args)`), checks the git commit is present,
creates a temporary git worktree at the recorded commit, imports the function via
`function_ref`, executes it via a `ReplayContext` with time-travel routing, saves and
returns the new record.

Raises `ConfigurationError` if a connection class cannot be imported or reconstructed.
Raises `MissingCommitError` if the recorded commit is not in the repository.

---

## Exceptions

| Exception | Parent | Raised when |
|---|---|---|
| `LineageError` | `Exception` | Base class for all library errors; also raised for git/JSON failures |
| `RunNotFoundError` | `LineageError` | `LineageStore.load()` called with an unknown `run_id` |
| `MissingInputError` | `LineageError` | `Replayer.replay()` finds one or more input files absent |
| `MissingCommitError` | `LineageError` | `Replayer.replay()` finds the recorded git commit missing |
| `UnsupportedOperationError` | `LineageError` | A `Connection` is asked to perform an operation it does not support (e.g. time travel on `LocalConnection`) |
| `TimeTravelError` | `LineageError` | A time-travel read cannot be satisfied (e.g. no S3 version exists at or before the requested timestamp) |
| `ConflictError` | `LineageError` | A conflict-free write would produce an output address that already exists (`overwrite=False`) |
| `ConfigurationError` | `LineageError` | A `Connection` is misconfigured or cannot be reconstructed by the `Replayer` |
| `DuplicateNameError` | `LineageError` | `open_input` or `open_output` is called with a name already in use within the same run |

---

## Disk Layout

```
<store_root>/
  <run_id>.json               # One JSON file per run (original or replay)

<base_output_dir>/
  <run_id>/
    <filename>                # Output files from an original run

<replay_root>/
  <orig_run_id>/
    <replay_run_id>/
      <filename>              # Output files from a replay run
```

Original and replay outputs are always in separate directory trees, so replaying a run
never overwrites the original outputs or any prior replay.
