# file-pipeline-lineage

## Table of Contents

- [What it does](#what-it-does)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Writing pipelines](#writing-pipelines)
- [Running tests](#running-tests)
- [API reference](#api-reference)

---

## What it does

`file_pipeline_lineage` wraps file-based data pipeline functions to record full lineage —
inputs, outputs, git commit, and enough metadata to replay any past run exactly.

---

## Installation

```bash
uv pip install -e ".[dev]"
```

---

## Quick start

```python
from pathlib import Path
from file_pipeline_lineage import LineageStore, Tracker, Replayer, RunContext

# 1. Define a pipeline function
def my_pipeline(ctx: RunContext) -> None:
    with ctx.open_input("data/input.csv") as f:
        data = f.read()
    with ctx.open_output("result.csv") as f:
        f.write(data)

# 2. Track a run — captures git commit, inputs, outputs
store = LineageStore("lineage_store")
tracker = Tracker(store)
record = tracker.track(my_pipeline, base_output_dir="outputs")
print(f"Run ID: {record.run_id}")
print(f"Outputs: {record.output_paths}")

# 3. Replay the run — re-executes at the recorded commit, isolated outputs
replayer = Replayer(store, replay_root="replays")
replay_record = replayer.replay(record.run_id)
print(f"Replay ID: {replay_record.run_id}")
print(f"Replay outputs: {replay_record.output_paths}")
```

---

## Writing pipelines

For lineage capture to work correctly, your pipeline function must follow these rules:

**Use `ctx` for all file I/O.** Any read or write that bypasses `ctx.open_input()` /
`ctx.open_output()` is invisible to the lineage system — it won't appear in the record
and won't be isolated per run.

**Define the function at module level.** Closures and lambdas can't be imported by
reference, so they can't be replayed. The function must be a named, module-level
definition in a Python file committed to git.

**Commit before tracking.** `Tracker` captures the current `HEAD` commit. If your
pipeline function isn't committed yet, replay will fail because the recorded commit
won't contain it.

**Keep it deterministic (for replay equivalence).** Replay re-runs the same function
against the same inputs. If the function is non-deterministic (e.g. uses random seeds
or timestamps), replay outputs will differ from the originals — which is valid, but
worth being aware of.

---

## Running tests

```bash
uv run pytest
```

---

## API reference

See [INTERFACES.md](INTERFACES.md) for complete documentation of all classes, methods,
type signatures, the `LineageRecord` field table, JSON schema, exception hierarchy,
and disk layout.
