# INTERFACES.md

## Table of Contents

- [Overview](#overview)
- [Pipeline Function Contract](#pipeline-function-contract)
  - [Required behaviour](#required-behaviour)
  - [Replay constraints](#replay-constraints)
- [Data Models](#data-models)
  - [LineageRecord Fields](#lineagerecord-fields)
- [JSON Schema](#json-schema)
- [Public API — RunContext](#public-api--runcontext)
  - [RunContext Constructor and Properties](#runcontext-constructor-and-properties)
  - [RunContext Methods](#runcontext-methods)
- [Public API — ReplayContext](#public-api--replaycontext)
- [Public API — LineageStore](#public-api--lineagestore)
- [Public API — Tracker](#public-api--tracker)
- [Public API — Replayer](#public-api--replayer)
- [Exceptions](#exceptions)
- [Disk Layout](#disk-layout)

---

## Overview

`file_pipeline_lineage` wraps file-based data pipeline functions to capture full lineage:
the git commit and importable reference of the code that ran, the files consumed, the files
produced, and enough metadata to replay any past run exactly.

All public names are importable directly from `file_pipeline_lineage`:

```python
from file_pipeline_lineage import (
    RunContext, ReplayContext, LineageRecord, LineageStore,
    Tracker, Replayer,
    LineageError, RunNotFoundError, MissingInputError, MissingCommitError,
)
```

---

## Pipeline Function Contract

A pipeline function must accept a single `RunContext` argument and return `None`.

```python
def my_pipeline(ctx: RunContext) -> None:
    with ctx.open_input("data/input.csv") as f:
        data = f.read()
    with ctx.open_output("result.csv") as f:
        f.write(data)
```

### Required behaviour

| Requirement | Detail |
|---|---|
| Signature | `(ctx: RunContext) -> None` |
| All reads | Must use `ctx.open_input()` — plain `open()` reads are invisible to lineage capture |
| All writes | Must use `ctx.open_output()` — plain `open()` writes are not recorded and not isolated per run |
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
| `input_paths` | `tuple[str, ...]` | Paths as provided to `ctx.open_input()` |
| `output_paths` | `tuple[str, ...]` | Resolved absolute paths constructed by `RunContext`/`ReplayContext` |
| `status` | `str` | `"success"` or `"failed"` |
| `exception_message` | `str \| None` | `None` on success; exception string on failure |
| `original_run_id` | `str \| None` | `None` for original runs; the replayed `run_id` for replay runs |

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
  "input_paths": ["<path>", "..."],
  "output_paths": ["<path>", "..."],
  "status": "success | failed",
  "exception_message": "<str> | null",
  "original_run_id": "<uuid4> | null"
}
```

`input_paths` and `output_paths` serialise as JSON arrays; they deserialise back to
`tuple[str, ...]`. Use `LineageRecord.to_dict()` / `LineageRecord.from_dict()` for
round-trip serialisation.

---

## Public API — RunContext

### RunContext Constructor and Properties

```python
class RunContext:
    def __init__(self, run_id: str, base_output_dir: str | Path) -> None: ...
```

| Parameter | Type | Description |
|---|---|---|
| `run_id` | `str` | Identifier for this run (UUID4 assigned by `Tracker`) |
| `base_output_dir` | `str \| Path` | Root directory under which output files are written |

| Property | Type | Description |
|---|---|---|
| `run_id` | `str` | The run identifier passed at construction |
| `inputs` | `tuple[str, ...]` | Immutable snapshot of all paths passed to `open_input()` |
| `outputs` | `tuple[str, ...]` | Immutable snapshot of all resolved paths from `open_output()` |

### RunContext Methods

```python
def open_input(self, path: str | Path, mode: str = "r", **kwargs) -> IO: ...
def open_output(self, path: str | Path, mode: str = "w", **kwargs) -> IO: ...
```

`open_input` — records `str(path)` in `inputs`, then delegates to the built-in `open()`.
All `mode` and `**kwargs` are forwarded unchanged.

`open_output` — resolves the destination to `<base_output_dir>/<run_id>/<filename>` (only
the basename of `path` is used). Creates parent directories, records the resolved path in
`outputs`, then delegates to `open()`.

---

## Public API — ReplayContext

`ReplayContext` is a subclass of `RunContext`. Only the constructor and `open_output` differ.

```python
class ReplayContext(RunContext):
    def __init__(
        self,
        run_id: str,
        orig_run_id: str,
        replay_root: str | Path,
    ) -> None: ...

    def open_output(self, path: str | Path, mode: str = "w", **kwargs) -> IO: ...
```

| Parameter | Description |
|---|---|
| `run_id` | UUID4 for this replay run |
| `orig_run_id` | `run_id` of the original run being replayed |
| `replay_root` | Root directory for all replay outputs |

`open_output` resolves to `<replay_root>/<orig_run_id>/<run_id>/<filename>`, ensuring
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

`replay` loads the original record, validates all input files exist, checks the git commit
is present, creates a temporary git worktree at the recorded commit, imports the function
via `function_ref`, executes it via a `ReplayContext`, saves and returns the new record.

Raises `MissingInputError` (listing all absent paths) before any execution if inputs are
missing. Raises `MissingCommitError` if the recorded commit is not in the repository.

---

## Exceptions

| Exception | Parent | Raised when |
|---|---|---|
| `LineageError` | `Exception` | Base class for all library errors; also raised for git/JSON failures |
| `RunNotFoundError` | `LineageError` | `LineageStore.load()` called with an unknown `run_id` |
| `MissingInputError` | `LineageError` | `Replayer.replay()` finds one or more input files absent |
| `MissingCommitError` | `LineageError` | `Replayer.replay()` finds the recorded git commit missing |

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
