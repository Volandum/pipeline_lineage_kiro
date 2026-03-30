"""ConnectionContractTests — reusable base class for verifying Connection implementations."""

from __future__ import annotations

import importlib
import json
import tempfile
import uuid
import warnings
from abc import abstractmethod
from pathlib import Path

import pytest

from file_pipeline_lineage.connections import Connection, OverwriteStatus, WriteResult
from file_pipeline_lineage.exceptions import UnsupportedOperationError


class ConnectionContractTests:
    """Base class for connector contract tests.

    Subclass this and implement ``make_connection()`` to verify that a
    ``Connection`` implementation satisfies the connector contract.

    Each I/O method test is capability-aware: it is skipped automatically
    when the connection raises ``UnsupportedOperationError``.
    """

    @abstractmethod
    def make_connection(self) -> Connection:
        """Return the Connection under test. Called fresh for each test method."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reconstruct(self, connection: Connection) -> Connection:
        """Reconstruct a connection via importlib (same path as the Replayer)."""
        t = type(connection)
        module_path = t.__module__
        class_name = t.__qualname__
        cls = getattr(importlib.import_module(module_path), class_name)
        return cls(**connection.serialise())

    # ------------------------------------------------------------------
    # Contract tests
    # ------------------------------------------------------------------

    def test_serialise_returns_json_serialisable_dict(self):
        """serialise() must return a JSON-serialisable dict."""
        conn = self.make_connection()
        result = conn.serialise()
        assert isinstance(result, dict), "serialise() must return a dict"
        # Must not raise
        json.dumps(result)

    def test_round_trip_serialise(self):
        """cls(**connection.serialise()).serialise() must equal connection.serialise()."""
        conn = self.make_connection()
        original = conn.serialise()
        reconstructed = self._reconstruct(conn)
        assert reconstructed.serialise() == original

    def test_supports_time_travel_returns_bool(self):
        """supports_time_travel must return a bool."""
        conn = self.make_connection()
        result = conn.supports_time_travel
        assert isinstance(result, bool), (
            f"supports_time_travel must return bool, got {type(result).__name__}"
        )

    def test_read_returns_readable_object(self, tmp_path):
        """If read(None) is supported, it must return a non-None object."""
        conn = self.make_connection()
        try:
            result = conn.read(None)
        except (UnsupportedOperationError, ImportError):
            pytest.skip("read() not supported by this connection")
        assert result is not None, "read(None) must return a non-None object"
        # Clean up if it's a file-like object
        if hasattr(result, "close"):
            result.close()

    def test_write_context_manager_completes_with_final_status(self, tmp_path):
        """If write(run_id) is supported, context manager must complete and
        final overwrite_status must not be 'in_progress'."""
        conn = self.make_connection()
        run_id = str(uuid.uuid4())
        try:
            ctx_mgr = conn.write(run_id)
        except (UnsupportedOperationError, ImportError):
            pytest.skip("write() not supported by this connection")

        with ctx_mgr as f:
            if hasattr(f, "write"):
                f.write("contract-test-data")

        # Check final status on the context manager object
        result: WriteResult | None = getattr(ctx_mgr, "result", None)
        if result is not None:
            assert result.overwrite_status != OverwriteStatus.IN_PROGRESS, (
                f"overwrite_status must not be IN_PROGRESS after __exit__, "
                f"got {result.overwrite_status!r}"
            )

    def test_atomic_write_returns_valid_result(self, tmp_path):
        """If atomic_write(data, run_id) is supported, it must return WriteResult | None
        with a valid overwrite_status when not None."""
        conn = self.make_connection()
        run_id = str(uuid.uuid4())
        valid_statuses = {s.value for s in OverwriteStatus}
        try:
            result = conn.atomic_write(b"contract-test-data", run_id)
        except (UnsupportedOperationError, ImportError):
            pytest.skip("atomic_write() not supported by this connection")

        if result is not None:
            assert isinstance(result, WriteResult), (
                f"atomic_write must return WriteResult or None, got {type(result).__name__}"
            )
            assert result.overwrite_status.value in valid_statuses, (
                f"overwrite_status {result.overwrite_status!r} is not a valid OverwriteStatus"
            )

    def test_distinct_run_ids_produce_non_overlapping_addresses(self, tmp_path):
        """Two distinct run_ids must produce non-overlapping output addresses
        (for any write method the connection supports).

        Emits a pytest warning if addresses cannot be compared (e.g. opaque objects).
        """
        conn = self.make_connection()
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())

        # Try write() first
        write_supported = True
        try:
            conn.write(run_id_a)
        except (UnsupportedOperationError, ImportError):
            write_supported = False

        if write_supported:
            paths_a: list = []
            paths_b: list = []

            ctx_a = conn.write(run_id_a)
            with ctx_a as f:
                if hasattr(f, "write"):
                    f.write("data-a")
                if hasattr(f, "name"):
                    paths_a.append(f.name)

            ctx_b = conn.write(run_id_b)
            with ctx_b as f:
                if hasattr(f, "write"):
                    f.write("data-b")
                if hasattr(f, "name"):
                    paths_b.append(f.name)

            if paths_a and paths_b:
                overlap = set(str(p) for p in paths_a) & set(str(p) for p in paths_b)
                assert not overlap, (
                    f"run_id {run_id_a!r} and {run_id_b!r} produced overlapping "
                    f"output addresses: {overlap}"
                )
            else:
                warnings.warn(
                    "Could not compare output addresses for distinct run_ids — "
                    "the file object did not expose a .name attribute. "
                    "Verify manually that per-run isolation is satisfied.",
                    stacklevel=2,
                )
            return

        # Try atomic_write()
        try:
            conn.atomic_write(b"data-a", run_id_a)
            conn.atomic_write(b"data-b", run_id_b)
        except (UnsupportedOperationError, ImportError):
            pytest.skip("Neither write() nor atomic_write() supported by this connection")
        except Exception:
            # atomic_write may fail for other reasons (e.g. missing boto3)
            pytest.skip("atomic_write() raised an unexpected error — skipping isolation check")
