"""End-to-end integration test: track → store → replay."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_pipeline_lineage import LineageStore, Replayer, Tracker


def test_end_to_end_track_and_replay(tmp_path, pipeline_git_repo, monkeypatch):
    """
    Full integration: track a pipeline, load the record, replay it.
    Asserts:
    - replay record has original_run_id set
    - output paths are distinct from original
    - both original and replay output files exist on disk
    Req 1.1, 3.2, 3.3, 3.4, 4.1, 4.3
    """
    monkeypatch.chdir(pipeline_git_repo.repo_path)

    # Track
    sys.path.insert(0, str(pipeline_git_repo.repo_path))
    try:
        import pipelines
        store = LineageStore(tmp_path / "store")
        tracker = Tracker(store)
        record = tracker.track(pipelines.simple_pipeline, tmp_path / "outputs")
    finally:
        sys.path.remove(str(pipeline_git_repo.repo_path))
        if "pipelines" in sys.modules:
            del sys.modules["pipelines"]

    # Load from store and verify
    loaded = store.load(record.run_id)
    assert loaded == record
    assert loaded.status == "success"
    assert loaded.original_run_id is None

    # Replay
    replayer = Replayer(store, tmp_path / "replays")
    replay_record = replayer.replay(record.run_id)

    # Replay record references original
    assert replay_record.original_run_id == record.run_id
    assert replay_record.run_id != record.run_id

    # Output paths are distinct — check via actual filesystem locations
    orig_run_dir = tmp_path / "outputs" / record.run_id
    replay_run_dir = tmp_path / "replays" / record.run_id / replay_record.run_id

    assert orig_run_dir.exists(), f"Original output dir missing: {orig_run_dir}"
    assert replay_run_dir.exists(), f"Replay output dir missing: {replay_run_dir}"

    orig_files = sorted(orig_run_dir.rglob("*"))
    replay_files = sorted(replay_run_dir.rglob("*"))

    assert len(orig_files) > 0
    assert len(replay_files) > 0

    # No overlap between original and replay output paths
    orig_strs = {str(f) for f in orig_files}
    for f in replay_files:
        assert str(f) not in orig_strs, f"Replay output overlaps with original: {f}"

    # Both original and replay outputs exist on disk (already confirmed above)
    for f in orig_files:
        assert f.exists(), f"Original output missing: {f}"
    for f in replay_files:
        assert f.exists(), f"Replay output missing: {f}"
