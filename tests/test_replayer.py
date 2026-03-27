"""Property-based tests for Replayer (Properties 8, 9, 11, 12, 13)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_pipeline_lineage import (
    LineageStore,
    MissingInputError,
    Replayer,
    Tracker,
)
from file_pipeline_lineage.record import LineageRecord


# ---------------------------------------------------------------------------
# Helper: import and track simple_pipeline from the fixture repo
# ---------------------------------------------------------------------------

def _track_simple_pipeline(pipeline_git_repo, store, output_dir, monkeypatch):
    """Track simple_pipeline from the fixture repo and return the LineageRecord."""
    monkeypatch.chdir(pipeline_git_repo.repo_path)
    sys.path.insert(0, str(pipeline_git_repo.repo_path))
    try:
        import pipelines  # noqa: PLC0415
        tracker = Tracker(store)
        return tracker.track(pipelines.simple_pipeline, output_dir)
    finally:
        sys.path.remove(str(pipeline_git_repo.repo_path))
        if "pipelines" in sys.modules:
            del sys.modules["pipelines"]


# ---------------------------------------------------------------------------
# Property 9: Replay output directory contains both run IDs
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 9: Replay output directory contains both run IDs
def test_replay_output_directory_contains_both_run_ids(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 3.3, 4.1, 4.2"""
    store = LineageStore(tmp_path / "store")
    record = _track_simple_pipeline(pipeline_git_repo, store, tmp_path / "outputs", monkeypatch)

    replayer = Replayer(store, tmp_path / "replays")
    replay_record = replayer.replay(record.run_id)

    # Every output path must be under <replay_root>/<orig_run_id>/<replay_run_id>/
    for output_path in replay_record.output_paths:
        p = Path(output_path)
        assert record.run_id in p.parts, (
            f"Original run_id '{record.run_id}' not found in path parts of '{p}'"
        )
        assert replay_record.run_id in p.parts, (
            f"Replay run_id '{replay_record.run_id}' not found in path parts of '{p}'"
        )
        # Must not overlap with original output paths
        assert output_path not in record.output_paths


# ---------------------------------------------------------------------------
# Property 11: Replay record references original run_id
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 11: Replay record references original run_id
def test_replay_record_references_original_run_id(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 3.4"""
    store = LineageStore(tmp_path / "store")
    record = _track_simple_pipeline(pipeline_git_repo, store, tmp_path / "outputs", monkeypatch)

    replayer = Replayer(store, tmp_path / "replays")
    replay_record = replayer.replay(record.run_id)

    assert replay_record.original_run_id == record.run_id
    assert replay_record.run_id != record.run_id


# ---------------------------------------------------------------------------
# Property 12: Missing inputs raise MissingInputError before execution
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 12: Missing inputs raise MissingInputError before execution
def test_missing_inputs_raise_before_execution(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 3.5"""
    monkeypatch.chdir(pipeline_git_repo.repo_path)
    store = LineageStore(tmp_path / "store")

    # Manually create a LineageRecord with a non-existent input path
    record = LineageRecord(
        run_id="00000000-0000-4000-8000-000000000001",
        timestamp_utc="2024-01-01T00:00:00+00:00",
        function_name="simple_pipeline",
        git_commit=pipeline_git_repo.commit_sha,
        function_ref=pipeline_git_repo.function_ref,
        input_paths=(str(tmp_path / "nonexistent_input.txt"),),
        output_paths=(),
        status="success",
        exception_message=None,
        original_run_id=None,
    )
    store.save(record)

    replayer = Replayer(store, tmp_path / "replays")
    with pytest.raises(MissingInputError) as exc_info:
        replayer.replay(record.run_id)

    assert "nonexistent_input.txt" in str(exc_info.value)
    # No output files should have been created
    replay_dir = tmp_path / "replays"
    assert not replay_dir.exists() or not any(replay_dir.rglob("*"))


# ---------------------------------------------------------------------------
# Property 13: Prior outputs are preserved after replay
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 13: Prior outputs are preserved after replay
def test_prior_outputs_preserved_after_replay(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 4.3"""
    store = LineageStore(tmp_path / "store")
    record = _track_simple_pipeline(pipeline_git_repo, store, tmp_path / "outputs", monkeypatch)

    # Record original output content
    original_outputs = {p: Path(p).read_bytes() for p in record.output_paths}

    replayer = Replayer(store, tmp_path / "replays")
    replayer.replay(record.run_id)

    # Original outputs must still exist with identical content
    for path, content in original_outputs.items():
        assert Path(path).exists(), f"Original output {path} was deleted"
        assert Path(path).read_bytes() == content, f"Original output {path} was modified"


# ---------------------------------------------------------------------------
# Property 8: Replay produces equivalent outputs
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 8: Replay produces equivalent outputs
def test_replay_produces_equivalent_outputs(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 3.2, 5.4"""
    store = LineageStore(tmp_path / "store")
    record = _track_simple_pipeline(pipeline_git_repo, store, tmp_path / "outputs", monkeypatch)

    replayer = Replayer(store, tmp_path / "replays")
    replay_record = replayer.replay(record.run_id)

    # Replay outputs must have same content as original outputs
    # (simple_pipeline writes deterministic content)
    assert len(replay_record.output_paths) == len(record.output_paths)
    for orig_path, replay_path in zip(sorted(record.output_paths), sorted(replay_record.output_paths)):
        assert Path(orig_path).read_bytes() == Path(replay_path).read_bytes()
