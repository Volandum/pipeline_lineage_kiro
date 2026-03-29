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
    # The sidecar is written relative to cwd (project root), which is stable
    # across both the original run and replay (worktree execution).
    _sidecar = Path.cwd() / ".demo_input_path"
    input_path = Path(_sidecar.read_text().strip())
    with ctx.open_input(input_path, "r") as f:
        content = f.read()
    with ctx.open_output("summary.txt", "w") as f:
        f.write(f"Lines: {len(content.splitlines())}\n")
    with ctx.open_output("copy.txt", "w") as f:
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

            # Track
            record = tracker.track(pipeline, tmp / "outputs")
            print(f"Run ID:        {record.run_id}")
            print(f"Output paths:  {list(record.output_paths)}")

            # Replay
            replayer = Replayer(store, tmp / "replays")
            replay_record = replayer.replay(record.run_id)
            print(f"Replay Run ID: {replay_record.run_id}")
            print(f"Replay outputs:{list(replay_record.output_paths)}")

            # Verify
            for p in record.output_paths:
                assert Path(p).exists(), f"MISSING original output: {p}"
            for p in replay_record.output_paths:
                assert Path(p).exists(), f"MISSING replay output: {p}"

            print("OK: all original and replay output files exist at distinct paths.")

        finally:
            sidecar.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
