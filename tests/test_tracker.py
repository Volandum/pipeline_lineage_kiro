"""Property-based tests for Tracker (Properties 1, 2, 3, 14)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.connections import LocalConnection
from file_pipeline_lineage.exceptions import LineageError
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
    input_content=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters=" \n")),
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
    input_file.write_text(input_content, encoding="utf-8")

    def pipeline(ctx):
        with ctx.open_input(LocalConnection(input_file)) as f:
            data = f.read()
        with ctx.open_output(LocalConnection(output_filename)) as f:
            f.write(data)

    store = LineageStore(tmp_path / "store")
    tracker = Tracker(store)
    record = tracker.track(pipeline, tmp_path / "outputs")

    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", record.run_id)
    assert record.status == "success"
    assert record.exception_message is None
    assert record.original_run_id is None
    # Check input descriptor contains the input file path
    assert len(record.inputs) == 1
    assert str(input_file.resolve()) == record.inputs[0].connection_args.get("path")
    # Check output descriptor exists
    assert len(record.outputs) == 1
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
            with ctx.open_output(LocalConnection("out.txt")) as f:
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
                with ctx.open_output(LocalConnection(f"out_{i}.txt")) as f:
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
        assert len(record.outputs) == n_outputs


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
            with ctx.open_output(LocalConnection("out.txt")) as f:
                f.write("hello")

        store = LineageStore(tmp / "store")
        tracker = Tracker(store)
        record = tracker.track(my_pipeline, tmp / "outputs")

        assert record.git_commit == expected_commit
        assert record.function_ref == f"{my_pipeline.__module__}:{my_pipeline.__qualname__}"
        assert record.function_name == "my_pipeline"


# ---------------------------------------------------------------------------
# Unit tests: success and failure paths
# ---------------------------------------------------------------------------

def test_tracker_success_path_known_pipeline(git_repo, monkeypatch, tmp_path):
    """A known pipeline produces a LineageRecord with expected field values. Req 1.1, 1.5, 5.1"""
    monkeypatch.chdir(git_repo)

    def known_pipeline(ctx):
        with ctx.open_output(LocalConnection("result.txt")) as f:
            f.write("known output")

    store = LineageStore(tmp_path / "store")
    tracker = Tracker(store)
    record = tracker.track(known_pipeline, tmp_path / "outputs")

    assert record.status == "success"
    assert record.function_name == "known_pipeline"
    assert record.exception_message is None
    assert record.original_run_id is None
    assert len(record.outputs) == 1
    # Output file must exist and contain expected content
    output_path = record.outputs[0].connection_args.get("path")
    assert output_path is not None
    # The actual written file is under base_output_dir/run_id/filename
    written_file = tmp_path / "outputs" / record.run_id / "result.txt"
    assert written_file.read_text(encoding="utf-8") == "known output"
    # Record must be persisted in store
    loaded = store.load(record.run_id)
    assert loaded == record


def test_tracker_raises_lineage_error_outside_git_repo(tmp_path, monkeypatch):
    """LineageError is raised when not in a git repo. Req 5.1"""
    # Use a temp dir that is definitely not a git repo
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    monkeypatch.chdir(non_repo)

    store = LineageStore(tmp_path / "store")
    tracker = Tracker(store)

    def pipeline(ctx):
        pass

    with pytest.raises(LineageError):
        tracker.track(pipeline, tmp_path / "outputs")
