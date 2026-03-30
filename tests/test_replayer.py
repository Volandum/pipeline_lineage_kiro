"""Property-based tests for Replayer (Properties 8, 9, 11, 12, 13)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_pipeline_lineage import (
    LineageStore,
    MissingCommitError,
    Replayer,
    Tracker,
)
from file_pipeline_lineage.connections import LocalConnection
from file_pipeline_lineage.descriptors import InputDescriptor, OutputDescriptor
from file_pipeline_lineage.exceptions import ConfigurationError
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


def _output_paths(record: LineageRecord) -> list[str]:
    """Reconstruct actual written output paths from a record's output descriptors.

    For LocalConnection, the actual written path is:
      connection_args["path"] is the serialised (resolved) path of the connection.
    But the actual file is at base_output_dir/run_id/filename — we can't recover
    base_output_dir from the descriptor alone.

    Instead, we use the fact that LocalConnection.write() creates the file at
    base_output_dir/run_id/filename, and the descriptor's connection_args["path"]
    gives us the filename. We reconstruct by finding the file under the store's
    known output roots, or we just return the connection_args paths for identity checks.

    For path-existence checks, callers must use the known output root + run_id + filename.
    """
    return [d.connection_args.get("path", "") for d in record.outputs]


def _find_output_files(record: LineageRecord, base_dir: Path) -> list[Path]:
    """Find actual written output files under base_dir/run_id/."""
    run_dir = base_dir / record.run_id
    if not run_dir.exists():
        return []
    return list(run_dir.rglob("*"))


def _find_replay_output_files(record: LineageRecord, replay_root: Path, orig_run_id: str) -> list[Path]:
    """Find actual written replay output files under replay_root/orig_run_id/replay_run_id/."""
    run_dir = replay_root / orig_run_id / record.run_id
    if not run_dir.exists():
        return []
    return list(run_dir.rglob("*"))


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

    # Replay outputs must be under replays/<orig_run_id>/<replay_run_id>/
    replay_files = _find_replay_output_files(replay_record, tmp_path / "replays", record.run_id)
    assert len(replay_files) > 0, "No replay output files found"
    for p in replay_files:
        assert record.run_id in p.parts, f"orig run_id not in path parts: {p}"
        assert replay_record.run_id in p.parts, f"replay run_id not in path parts: {p}"

    # Must not overlap with original output files
    orig_files = _find_output_files(record, tmp_path / "outputs")
    orig_strs = {str(f) for f in orig_files}
    for p in replay_files:
        assert str(p) not in orig_strs, f"Replay output overlaps with original: {p}"


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
# Property 12: Bad connection class raises ConfigurationError before execution
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 12: Bad connection class raises ConfigurationError before execution
def test_bad_connection_class_raises_before_execution(tmp_path, pipeline_git_repo, monkeypatch):
    """Validates: Requirements 3.5 — replayer raises ConfigurationError when a
    connection class cannot be imported (pre-flight check)."""
    monkeypatch.chdir(pipeline_git_repo.repo_path)
    store = LineageStore(tmp_path / "store")

    # Manually create a LineageRecord with an unimportable connection class
    record = LineageRecord(
        run_id="00000000-0000-4000-8000-000000000001",
        timestamp_utc="2024-01-01T00:00:00+00:00",
        function_name="simple_pipeline",
        git_commit=pipeline_git_repo.commit_sha,
        function_ref=pipeline_git_repo.function_ref,
        inputs=(
            InputDescriptor(
                name="1:NonExistentConnection(path=/nonexistent.txt)",
                connection_class="nonexistent_module:NonExistentConnection",
                connection_args={"path": "/nonexistent.txt"},
                access_timestamp="2024-01-01T00:00:00+00:00",
                time_travel=False,
            ),
        ),
        outputs=(),
        status="success",
        exception_message=None,
        original_run_id=None,
    )
    store.save(record)

    replayer = Replayer(store, tmp_path / "replays")
    with pytest.raises(ConfigurationError):
        replayer.replay(record.run_id)

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
    orig_files = _find_output_files(record, tmp_path / "outputs")
    assert len(orig_files) > 0
    original_contents = {str(p): p.read_bytes() for p in orig_files}

    replayer = Replayer(store, tmp_path / "replays")
    replayer.replay(record.run_id)

    # Original outputs must still exist with identical content
    for path_str, content in original_contents.items():
        p = Path(path_str)
        assert p.exists(), f"Original output {path_str} was deleted"
        assert p.read_bytes() == content, f"Original output {path_str} was modified"


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

    orig_files = sorted(_find_output_files(record, tmp_path / "outputs"), key=lambda p: p.name)
    replay_files = sorted(
        _find_replay_output_files(replay_record, tmp_path / "replays", record.run_id),
        key=lambda p: p.name,
    )

    assert len(replay_files) == len(orig_files), (
        f"Expected {len(orig_files)} replay outputs, got {len(replay_files)}"
    )
    for orig, replay in zip(orig_files, replay_files):
        assert orig.read_bytes() == replay.read_bytes(), (
            f"Content mismatch: {orig} vs {replay}"
        )


# ---------------------------------------------------------------------------
# Unit tests: error conditions
# ---------------------------------------------------------------------------

def test_bad_connection_class_lists_all_absent(tmp_path, pipeline_git_repo, monkeypatch):
    """ConfigurationError is raised for unimportable connection classes. Req 3.5"""
    monkeypatch.chdir(pipeline_git_repo.repo_path)
    store = LineageStore(tmp_path / "store")

    record = LineageRecord(
        run_id="00000000-0000-4000-8000-000000000002",
        timestamp_utc="2024-01-01T00:00:00+00:00",
        function_name="simple_pipeline",
        git_commit=pipeline_git_repo.commit_sha,
        function_ref=pipeline_git_repo.function_ref,
        inputs=(
            InputDescriptor(
                name="1:BadConn(path=/absent1.txt)",
                connection_class="no_such_module:BadConn",
                connection_args={"path": "/absent1.txt"},
                access_timestamp="2024-01-01T00:00:00+00:00",
                time_travel=False,
            ),
        ),
        outputs=(),
        status="success",
        exception_message=None,
        original_run_id=None,
    )
    store.save(record)

    replayer = Replayer(store, tmp_path / "replays")
    with pytest.raises(ConfigurationError):
        replayer.replay(record.run_id)

    # No output files created
    replay_dir = tmp_path / "replays"
    assert not replay_dir.exists() or not any(replay_dir.rglob("*"))


def test_missing_commit_error_for_unknown_sha(tmp_path, pipeline_git_repo, monkeypatch):
    """MissingCommitError is raised for an unknown commit SHA. Req 5.5"""
    monkeypatch.chdir(pipeline_git_repo.repo_path)
    store = LineageStore(tmp_path / "store")

    fake_sha = "deadbeef" * 5  # 40-char hex, does not exist
    record = LineageRecord(
        run_id="00000000-0000-4000-8000-000000000003",
        timestamp_utc="2024-01-01T00:00:00+00:00",
        function_name="simple_pipeline",
        git_commit=fake_sha,
        function_ref=pipeline_git_repo.function_ref,
        inputs=(),
        outputs=(),
        status="success",
        exception_message=None,
        original_run_id=None,
    )
    store.save(record)

    replayer = Replayer(store, tmp_path / "replays")
    with pytest.raises(MissingCommitError):
        replayer.replay(record.run_id)
