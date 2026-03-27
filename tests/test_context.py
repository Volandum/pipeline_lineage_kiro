"""Property-based tests for RunContext and ReplayContext (Properties 9, 10)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.context import ReplayContext, RunContext

# Windows reserved device names that cannot be used as filenames
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


# ---------------------------------------------------------------------------
# Property 10: RunContext constructs output paths under base_output_dir/run_id
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 10: RunContext constructs output paths under base_output_dir/run_id
@given(
    run_id=st.uuids().map(str),
    filename=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="._-",
        ),
    ),
    content=st.binary(min_size=0, max_size=100),
)
@settings(max_examples=200)
def test_run_context_output_path_construction(run_id, filename, content):
    """Validates: Requirements 7.4"""
    assume(filename.upper() not in _WINDOWS_RESERVED)
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        ctx = RunContext(run_id, base)
        with ctx.open_output(filename, mode="wb") as f:
            f.write(content)
        expected = base / run_id / filename
        assert expected.exists()
        assert str(expected) in ctx.outputs
        assert expected.read_bytes() == content


# ---------------------------------------------------------------------------
# Property 9: Replay output directory contains both run IDs
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 9: Replay output directory contains both run IDs
@given(
    orig_run_id=st.uuids().map(str),
    replay_run_id=st.uuids().map(str),
    filename=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="._-",
        ),
    ),
    content=st.binary(min_size=0, max_size=100),
)
@settings(max_examples=200)
def test_replay_context_output_path_isolation(orig_run_id, replay_run_id, filename, content):
    """Validates: Requirements 3.3, 4.1, 4.2"""
    assume(filename.upper() not in _WINDOWS_RESERVED)
    with tempfile.TemporaryDirectory() as d:
        replay_root = Path(d)
        ctx = ReplayContext(replay_run_id, orig_run_id, replay_root)
        with ctx.open_output(filename, mode="wb") as f:
            f.write(content)
        expected = replay_root / orig_run_id / replay_run_id / filename
        assert expected.exists()
        assert str(expected) in ctx.outputs
        # Must not overlap with a RunContext path for the same filename
        run_ctx_path = replay_root / replay_run_id / filename
        assert not run_ctx_path.exists()
