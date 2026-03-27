"""Property-based tests for Tracker (Properties 1, 2, 3, 14)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.store import LineageStore
from file_pipeline_lineage.tracker import Tracker


# ---------------------------------------------------------------------------
# Fixture: temporary git repository
# ---------------------------------------------------------------------------

@pytest.fixture()
def git_repo(tmp_path_factory):
    """Create a minimal git repo with one commit and return its path."""
    repo = tmp_path_factory.mktemp("git_repo")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    dummy = repo / "dummy.txt"
    dummy.write_text("init")
    subprocess.run(["git", "add", "dummy.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


# ---------------------------------------------------------------------------
# Property 1: LineageRecord completeness
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 1: LineageRecord completeness
@given(
    input_content=st.binary(min_size=1, max_size=100),
    output_filename=st.just("output.bin"),
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_lineage_record_completeness(tmp_path, git_repo, monkeypatch, input_content, output_filename):
    """Validates: Requirements 1.1, 1.3, 1.4, 1.6"""
    import re
    monkeypatch.chdir(git_repo)
    input_file = tmp_path / "input.bin"
    input_file.write_bytes(input_content)

    def pipeline(ctx):
        with ctx.open_input(input_file, "rb") as f:
            data = f.read()
        with ctx.open_output(output_filename, "wb") as f:
            f.write(data)

    store = LineageStore(tmp_path / "store")
    tracker = Tracker(store)
    record = tracker.track(pipeline, tmp_path / "outputs")

    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", record.run_id)
    assert record.status == "success"
    assert record.exception_message is None
    assert record.original_run_id is None
    assert str(input_file) in record.input_paths
    assert len(record.output_paths) == 1
    assert record.git_commit  # non-empty
    assert ":" in record.function_ref


# ---------------------------------------------------------------------------
# Property 2: Run_ID uniqueness
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 2: Run_ID uniqueness
def test_run_id_uniqueness(git_repo, monkeypatch):
    """Validates: Requirements 1.2, 7.1"""
    monkeypatch.chdir(git_repo)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def pipeline(ctx):
            with ctx.open_output("out.txt") as f:
                f.write("x")

        store = LineageStore(tmp / "store")
        tracker = Tracker(store)
        run_ids = [tracker.track(pipeline, tmp / "outputs").run_id for _ in range(20)]
        assert len(set(run_ids)) == 20


# ---------------------------------------------------------------------------
# Property 3: Failed run captures partial outputs and re-raises
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 3: Failed run captures partial outputs and re-raises
@given(n_outputs=st.integers(min_value=0, max_value=4))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_failed_run_captures_partial_outputs(git_repo, monkeypatch, n_outputs):
    """Validates: Requirements 1.5"""
    monkeypatch.chdir(git_repo)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def pipeline(ctx):
            for i in range(n_outputs):
                with ctx.open_output(f"out_{i}.txt") as f:
                    f.write(f"output {i}")
            raise ValueError("deliberate failure")

        store = LineageStore(tmp / "store")
        tracker = Tracker(store)
        with pytest.raises(ValueError, match="deliberate failure"):
            tracker.track(pipeline, tmp / "outputs")

        run_ids = store.list_run_ids()
        assert len(run_ids) == 1
        record = store.load(run_ids[0])
        assert record.status == "failed"
        assert "deliberate failure" in record.exception_message
        assert len(record.output_paths) == n_outputs


# ---------------------------------------------------------------------------
# Property 14: git_commit and function_ref are captured correctly
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 14: git_commit and function_ref are captured correctly
def test_git_commit_and_function_ref_captured(git_repo, monkeypatch):
    """Validates: Requirements 5.1, 5.2"""
    monkeypatch.chdir(git_repo)

    import subprocess as sp
    expected_commit = sp.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=git_repo,
    ).stdout.strip()

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def my_pipeline(ctx):
            with ctx.open_output("out.txt") as f:
                f.write("hello")

        store = LineageStore(tmp / "store")
        tracker = Tracker(store)
        record = tracker.track(my_pipeline, tmp / "outputs")

        assert record.git_commit == expected_commit
        assert record.function_ref == f"{my_pipeline.__module__}:{my_pipeline.__qualname__}"
        assert record.function_name == "my_pipeline"
