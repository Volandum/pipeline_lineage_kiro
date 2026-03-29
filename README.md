# file-pipeline-lineage

## Table of Contents

- [What it does](#what-it-does)
- [Installation](#installation)
- [Quick start](#quick-start)
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

## Running tests

```bash
uv run pytest
```

---

## API reference

See [INTERFACES.md](INTERFACES.md) for complete documentation of all classes, methods,
type signatures, the `LineageRecord` field table, JSON schema, exception hierarchy,
and disk layout.
