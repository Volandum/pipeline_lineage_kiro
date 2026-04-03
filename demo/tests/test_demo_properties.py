"""Integration property tests for demo-notebook (Properties 5 and 6).

These tests require a real git repository with demo/pipeline.py committed.
They are tagged @pytest.mark.integration and skipped if not in a git repo.
"""

import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from demo.pipeline import MockS3Connection, SimulatedDBConnection, run_pipeline
from file_pipeline_lineage import LineageStore, Tracker


def _in_git_repo() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
    )
    return result.returncode == 0


def _seed_db(db_path: Path, rows: list) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value REAL, label TEXT)")
        conn.executemany("INSERT INTO records VALUES (?, ?, ?)", rows)


@pytest.mark.integration
@pytest.mark.skipif(not _in_git_repo(), reason="requires git repository")
@given(
    rows=st.lists(
        st.tuples(
            st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.text(min_size=1, max_size=8, alphabet="abcdefghijklmnopqrstuvwxyz"),
        ),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=5)
def test_tracker_produces_complete_lineage_record(rows):
    """Property 5: Tracker produces a complete LineageRecord."""
    import demo.pipeline as pipeline_module

    indexed_rows = [(i + 1, value, label) for i, (value, label) in enumerate(rows)]
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        db_path = tmp_dir / "records.db"
        _seed_db(db_path, indexed_rows)
        pipeline_module.DB_PATH = str(db_path)

        store = LineageStore(tmp_dir / "store")
        tracker = Tracker(store)
        record = tracker.track(run_pipeline, tmp_dir / "outputs")

        # status
        assert record.status == "success"
        # exactly one input descriptor identifying SimulatedDBConnection
        assert len(record.inputs) == 1
        assert "SimulatedDBConnection" in record.inputs[0].connection_class
        # exactly one output descriptor identifying MockS3Connection
        assert len(record.outputs) == 1
        assert "MockS3Connection" in record.outputs[0].connection_class
        # 40-char hex git_commit
        assert re.fullmatch(r"[0-9a-f]{40}", record.git_commit)
        # function_ref in "module:qualname" format
        assert ":" in record.function_ref
        module_part, qualname_part = record.function_ref.split(":", 1)
        assert module_part and qualname_part
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.skipif(not _in_git_repo(), reason="requires git repository")
@given(
    rows=st.lists(
        st.tuples(
            st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.text(min_size=1, max_size=8, alphabet="abcdefghijklmnopqrstuvwxyz"),
        ),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=3)
def test_replay_produces_matching_outputs(rows):
    """Property 6: Replay produces matching outputs."""
    import importlib
    import sys
    import unittest.mock as mock
    import demo.pipeline as pipeline_module
    from file_pipeline_lineage import Replayer

    indexed_rows = [(i + 1, value, label) for i, (value, label) in enumerate(rows)]
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        db_path = tmp_dir / "records.db"
        _seed_db(db_path, indexed_rows)
        pipeline_module.DB_PATH = str(db_path)

        store = LineageStore(tmp_dir / "store")
        tracker = Tracker(store)
        replayer = Replayer(store, tmp_dir / "replays")

        record = tracker.track(run_pipeline, tmp_dir / "outputs")

        # The Replayer imports demo.pipeline fresh from a git worktree, so DB_PATH
        # resets to "". Wrap importlib.import_module to inject DB_PATH after import.
        _real_import = importlib.import_module

        def _patched_import(name, *args, **kwargs):
            mod = _real_import(name, *args, **kwargs)
            if name == "demo.pipeline":
                mod.DB_PATH = str(db_path)
            return mod

        with mock.patch("importlib.import_module", side_effect=_patched_import):
            replay_record = replayer.replay(record.run_id)

        # status
        assert replay_record.status == "success", f"Replay failed: {replay_record.exception_message}"
        # original_run_id links back to original
        assert replay_record.original_run_id == record.run_id
        # distinct run_id
        assert replay_record.run_id != record.run_id
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
