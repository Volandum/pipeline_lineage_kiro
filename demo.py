#!/usr/bin/env python
"""demo.py — end-to-end demonstration of file_pipeline_lineage.

Run from the project root (must be inside a git repository):
    python demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Pipeline function — must be at module level so it is importable by function_ref
# ---------------------------------------------------------------------------

def pipeline(ctx):
    """Read one input file, write two output files."""
    # Sidecar written relative to cwd (project root) — stable across runs/replays.
    _input_sidecar = Path.cwd() / ".demo_input_path"
    input_path = Path(_input_sidecar.read_text().strip())

    from file_pipeline_lineage.connections import LocalConnection

    with ctx.open_input(LocalConnection(input_path)) as f:
        content = f.read()
    # base_output_dir is injected by RunContext from the output_dir passed to track()
    with ctx.open_output(LocalConnection("summary.txt")) as f:
        f.write(f"Lines: {len(content.splitlines())}\n")
    with ctx.open_output(LocalConnection("copy.txt")) as f:
        f.write(content)


# Ensure function_ref resolves to "demo:pipeline" even when run as __main__
pipeline.__module__ = "demo"


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def main():
    from file_pipeline_lineage import LineageStore, Replayer, Tracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create input file
        input_file = tmp / "input.txt"
        input_file.write_text("hello\nworld\nfrom demo\n")

        # Write sidecar so pipeline() can find the input path
        sidecar = Path.cwd() / ".demo_input_path"
        sidecar.write_text(str(input_file))

        try:
            store = LineageStore(tmp / "store")
            tracker = Tracker(store)

            # Track — RunContext injects tmp/"outputs" as base_output_dir
            record = tracker.track(pipeline, tmp / "outputs")
            # Actual output files are under tmp/outputs/<run_id>/
            orig_files = list((tmp / "outputs" / record.run_id).rglob("*"))
            print(f"Run ID:        {record.run_id}")
            print(f"Output files:  {[str(f) for f in orig_files]}")

            # Replay
            replayer = Replayer(store, tmp / "replays")
            replay_record = replayer.replay(record.run_id)
            # Actual replay files are under tmp/replays/<orig_run_id>/<replay_run_id>/
            replay_files = list(
                (tmp / "replays" / record.run_id / replay_record.run_id).rglob("*")
            )
            print(f"Replay Run ID: {replay_record.run_id}")
            print(f"Replay files:  {[str(f) for f in replay_files]}")

            # Verify
            for f in orig_files:
                assert f.exists(), f"MISSING original output: {f}"
            for f in replay_files:
                assert f.exists(), f"MISSING replay output: {f}"

            print("OK: all original and replay output files exist at distinct paths.")

        finally:
            sidecar.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
