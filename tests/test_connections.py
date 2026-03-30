"""Tests for Connection ABC and built-in connectors."""

from __future__ import annotations

import importlib

from hypothesis import given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.connections import LocalConnection

# Windows reserved device names that cause Path.resolve() to hang
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# ---------------------------------------------------------------------------
# Property 6: Connection reconstruction round-trip
# Feature: generalised-connections, Property 6: Connection reconstruction round-trip
# ---------------------------------------------------------------------------

# Safe path characters: alphanumeric, underscores, dots — filter reserved names
_safe_path = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_."),
    min_size=1,
    max_size=50,
).filter(lambda p: p.upper() not in _WINDOWS_RESERVED)


# Feature: generalised-connections, Property 6: Connection reconstruction round-trip
@given(path=_safe_path)
@settings(max_examples=200, deadline=None)
def test_local_connection_reconstruction_round_trip(path: str) -> None:
    """cls(**c.serialise()) must produce a connection whose serialise() equals the original.

    Validates: Requirements 10.1, 10.3
    """
    original = LocalConnection(path)
    serialised = original.serialise()

    # Reconstruct via importlib (same path the Replayer uses)
    connection_class = (
        f"{type(original).__module__}:{type(original).__qualname__}"
    )
    module_path, class_name = connection_class.split(":", 1)
    cls = getattr(importlib.import_module(module_path), class_name)
    reconstructed = cls(**serialised)

    assert reconstructed.serialise() == serialised


# ---------------------------------------------------------------------------
# Task 8.1 / 8.2: ConnectionContractTests — LocalConnection subclass
# ---------------------------------------------------------------------------

import tempfile
import uuid
from pathlib import Path

import pytest

from file_pipeline_lineage.connections import OverwriteStatus, S3Connection
from file_pipeline_lineage.contract import ConnectionContractTests


class TestLocalConnectionContract(ConnectionContractTests):
    """Reference demo of ConnectionContractTests usage for LocalConnection."""

    def make_connection(self):
        # Use a real temp directory so read/write tests work
        base = Path(tempfile.mkdtemp())
        src = base / "source.txt"
        src.write_text("hello contract", encoding="utf-8")
        return LocalConnection(path=src, base_output_dir=base)

    def test_read_returns_readable_object(self, tmp_path):
        conn = self.make_connection()
        result = conn.read(None)
        assert result is not None
        result.close()

    def test_write_context_manager_completes_with_final_status(self, tmp_path):
        base = Path(tempfile.mkdtemp())
        src = base / "source.txt"
        src.write_text("hello", encoding="utf-8")
        conn = LocalConnection(path=src, base_output_dir=base)
        run_id = str(uuid.uuid4())
        ctx_mgr = conn.write(run_id)
        with ctx_mgr as f:
            f.write("data")
        assert ctx_mgr.result is not None
        assert ctx_mgr.result.overwrite_status != OverwriteStatus.IN_PROGRESS

    def test_distinct_run_ids_produce_non_overlapping_addresses(self, tmp_path):
        base = Path(tempfile.mkdtemp())
        src = base / "source.txt"
        src.write_text("hello", encoding="utf-8")
        conn = LocalConnection(path=src, base_output_dir=base)
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())
        paths_a = []
        paths_b = []
        with conn.write(run_id_a) as f:
            f.write("a")
            paths_a.append(f.name)
        with conn.write(run_id_b) as f:
            f.write("b")
            paths_b.append(f.name)
        overlap = set(str(p) for p in paths_a) & set(str(p) for p in paths_b)
        assert not overlap


# ---------------------------------------------------------------------------
# Task 8.3: S3ConnectionContractTests
# ---------------------------------------------------------------------------

class TestS3ConnectionContract(ConnectionContractTests):
    """Contract tests for S3Connection.

    Only serialise(), round-trip, and supports_time_travel run here —
    read() and atomic_write() require boto3 so they are skipped by the
    capability check (ImportError is treated as unsupported).
    write() and atomic_read() raise UnsupportedOperationError and are skipped.
    """

    def make_connection(self):
        return S3Connection(bucket="test-bucket", key="test/key.csv", time_travel=False)


# ---------------------------------------------------------------------------
# Shared strategy for safe filenames (used by Properties 7 and 9)
# ---------------------------------------------------------------------------

from hypothesis import given, settings
from hypothesis import strategies as st

safe_filename_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_."),
    min_size=1,
    max_size=30,
).filter(lambda p: p.upper() not in _WINDOWS_RESERVED and not p.startswith("."))


# ---------------------------------------------------------------------------
# Property 7: LocalConnection write path structure
# Feature: generalised-connections, Property 7: LocalConnection write path structure
# ---------------------------------------------------------------------------

@given(run_id=st.uuids().map(str), filename=safe_filename_strategy)
@settings(max_examples=100, deadline=None)
def test_local_connection_write_path_contains_run_id(run_id, filename):
    """Output path must contain run_id as a directory segment.

    Validates: Requirements 2.3, 7.1
    """
    import tempfile as _tempfile
    tmp = Path(_tempfile.mkdtemp())
    conn = LocalConnection(path=tmp / filename, base_output_dir=tmp)
    with conn.write(run_id) as f:
        f.write("data")
    output_files = list(tmp.rglob(filename))
    assert any(run_id in str(p) for p in output_files)


# ---------------------------------------------------------------------------
# Property 8: LocalConnection read round-trip
# Feature: generalised-connections, Property 8: LocalConnection read round-trip
# ---------------------------------------------------------------------------

@given(content=st.text(min_size=0, max_size=500))
@settings(max_examples=100, deadline=None)
def test_local_connection_read_round_trip(content):
    """read(None) must return a file-like object whose content equals the original.

    Validates: Requirements 2.2
    """
    import tempfile as _tempfile
    tmp = Path(_tempfile.mkdtemp())
    p = tmp / "test.txt"
    # Write with newline="" so no platform translation occurs
    p.write_text(content, encoding="utf-8", newline="")
    conn = LocalConnection(path=p)
    f = conn.read(None)
    result = f.read()
    f.close()
    assert result == content


# ---------------------------------------------------------------------------
# Property 9: IN_PROGRESS → final status transition
# Feature: generalised-connections, Property 9: IN_PROGRESS transitions to final status
# ---------------------------------------------------------------------------

from file_pipeline_lineage.context import RunContext


@given(run_id=st.uuids().map(str), filename=safe_filename_strategy)
@settings(max_examples=100, deadline=None)
def test_in_progress_transitions_to_final_status(run_id, filename):
    """overwrite_status must be 'in_progress' while open and final after __exit__.

    Validates: Requirements 7.8, 7.9
    """
    import tempfile as _tempfile
    tmp = Path(_tempfile.mkdtemp())
    conn = LocalConnection(path=tmp / filename, base_output_dir=tmp)
    ctx = RunContext(run_id=run_id, base_output_dir=tmp)

    with ctx.open_output(conn) as f:
        f.write("data")
        # While open: status should be in_progress
        assert ctx.outputs[0].overwrite_status == "in_progress"

    # After close: status must be final
    assert ctx.outputs[0].overwrite_status in ("no_overwrite", "overwrite")
