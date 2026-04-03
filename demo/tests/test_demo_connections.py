"""Unit and property tests for SimulatedDBConnection."""

import sqlite3
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from demo.pipeline import SimulatedDBConnection
from file_pipeline_lineage import UnsupportedOperationError


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_db(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, value REAL, label TEXT)"
        )
        conn.executemany(
            "INSERT INTO records VALUES (?, ?, ?)",
            [(1, 10.5, "a"), (2, -3.0, "b"), (3, 7.2, "c")],
        )
    return str(db_path)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_simulated_db_atomic_read_returns_dataframe(sqlite_db):
    conn = SimulatedDBConnection(sqlite_db)
    df = conn.atomic_read(None)
    assert list(df.columns) == ["id", "value", "label"]
    assert len(df) == 3


def test_simulated_db_atomic_read_timestamp_raises(sqlite_db):
    conn = SimulatedDBConnection(sqlite_db)
    with pytest.raises(UnsupportedOperationError):
        conn.atomic_read("2024-01-01T00:00:00+00:00")


def test_simulated_db_serialise(sqlite_db):
    conn = SimulatedDBConnection(sqlite_db)
    assert conn.serialise() == {"db_path": str(Path(sqlite_db).resolve())}


# ---------------------------------------------------------------------------
# Property test — serialise round-trip
# Validates: Requirements 2.3, 2.4
# ---------------------------------------------------------------------------

@given(st.text(min_size=1))
@settings(max_examples=100)
def test_simulated_db_serialise_round_trip(db_path):
    """Property 1: SimulatedDBConnection serialise round-trip."""
    conn = SimulatedDBConnection(db_path)
    assert SimulatedDBConnection(**conn.serialise()).serialise() == conn.serialise()


# ---------------------------------------------------------------------------
# MockS3Connection imports
# ---------------------------------------------------------------------------

from demo.pipeline import MockS3Connection
from file_pipeline_lineage import OverwriteStatus, WriteResult


# ---------------------------------------------------------------------------
# Unit tests — MockS3Connection (Task 3.2)
# ---------------------------------------------------------------------------

def test_mock_s3_atomic_write_no_overwrite():
    conn = MockS3Connection(bucket="b", key="output/results.csv")
    result = conn.atomic_write(b"data", run_id="run-1")
    assert result == WriteResult(OverwriteStatus.NO_OVERWRITE)


def test_mock_s3_atomic_write_overwrite():
    conn = MockS3Connection(bucket="b", key="output/results.csv")
    conn.atomic_write(b"data", run_id="run-1")
    result = conn.atomic_write(b"data2", run_id="run-1")
    assert result == WriteResult(OverwriteStatus.OVERWRITE)


def test_mock_s3_serialise_shape():
    conn = MockS3Connection(bucket="my-bucket", key="path/to/file.csv", time_travel=True)
    s = conn.serialise()
    assert set(s.keys()) == {"bucket", "key", "time_travel"}


# ---------------------------------------------------------------------------
# Property test — MockS3Connection serialise round-trip (Task 3.3)
# Validates: Requirements 3.3, 3.4
# ---------------------------------------------------------------------------

@given(
    bucket=st.text(min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-")),
    key=st.text(min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-/")),
    time_travel=st.booleans(),
)
@settings(max_examples=100)
def test_mock_s3_serialise_round_trip(bucket, key, time_travel):
    """Property 2: MockS3Connection serialise round-trip."""
    conn = MockS3Connection(bucket=bucket, key=key, time_travel=time_travel)
    assert MockS3Connection(**conn.serialise()).serialise() == conn.serialise()


# ---------------------------------------------------------------------------
# Property test — MockS3Connection overwrite status (Task 3.4)
# Validates: Requirements 3.6
# ---------------------------------------------------------------------------

@given(
    bucket=st.just("demo-bucket"),
    key=st.just("output/results.csv"),
    run_id=st.uuids().map(str),
    data=st.binary(min_size=1),
)
@settings(max_examples=50)
def test_mock_s3_overwrite_status(bucket, key, run_id, data):
    """Property 4: MockS3Connection overwrite status is correct."""
    conn = MockS3Connection(bucket=bucket, key=key)
    result1 = conn.atomic_write(data, run_id=run_id)
    assert result1.overwrite_status == OverwriteStatus.NO_OVERWRITE
    result2 = conn.atomic_write(data, run_id=run_id)
    assert result2.overwrite_status == OverwriteStatus.OVERWRITE


# ---------------------------------------------------------------------------
# ConnectionContractTests subclasses (Task 4)
# ---------------------------------------------------------------------------

import tempfile

from file_pipeline_lineage.contract import ConnectionContractTests


class TestSimulatedDBConnectionContract(ConnectionContractTests):
    """Verify SimulatedDBConnection satisfies the Connection contract."""

    def setup_method(self, method):
        import shutil
        self._tmp_dir = tempfile.mkdtemp()
        self._cleanup = lambda: shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def teardown_method(self, method):
        self._cleanup()

    def make_connection(self) -> SimulatedDBConnection:
        db_path = Path(self._tmp_dir) / "contract_test.db"
        if not db_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE records (id INTEGER PRIMARY KEY, value REAL, label TEXT)"
                )
                conn.executemany(
                    "INSERT INTO records VALUES (?, ?, ?)",
                    [(1, 10.5, "a"), (2, -3.0, "b"), (3, 7.2, "c")],
                )
        return SimulatedDBConnection(str(db_path))


class TestMockS3ConnectionContract(ConnectionContractTests):
    """Verify MockS3Connection satisfies the Connection contract."""

    def make_connection(self) -> MockS3Connection:
        return MockS3Connection(bucket="test-bucket", key="output/test.csv")


# ---------------------------------------------------------------------------
# Property test — pipeline output determinism (Task 5.2)
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------

import uuid
import unittest.mock as mock

from file_pipeline_lineage import RunContext


@given(
    rows=st.lists(
        st.tuples(
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=50)
def test_run_pipeline_output_is_deterministic(rows):
    """Property 3: Pipeline output is deterministic."""
    import tempfile
    import demo.pipeline as pipeline_module

    # Use auto-incrementing IDs to avoid UNIQUE constraint violations
    indexed_rows = [(i + 1, value, label) for i, (value, label) in enumerate(rows)]

    tmp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(tmp_dir) / "det_test.db"
        db_conn = sqlite3.connect(db_path)
        try:
            db_conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value REAL, label TEXT)")
            db_conn.executemany("INSERT INTO records VALUES (?, ?, ?)", indexed_rows)
            db_conn.commit()
        finally:
            db_conn.close()

        pipeline_module.DB_PATH = str(db_path)

        written = []
        original_atomic_write = MockS3Connection.atomic_write

        def capturing_write(self, data, run_id, overwrite=False):
            written.append(data)
            return original_atomic_write(self, data, run_id=run_id, overwrite=overwrite)

        with mock.patch.object(MockS3Connection, "atomic_write", capturing_write):
            ctx1 = RunContext(run_id=str(uuid.uuid4()))
            ctx2 = RunContext(run_id=str(uuid.uuid4()))

            from demo.pipeline import run_pipeline
            run_pipeline(ctx1)
            run_pipeline(ctx2)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    assert len(written) == 2
    assert written[0] == written[1], "Pipeline output must be byte-for-byte identical for same input"
