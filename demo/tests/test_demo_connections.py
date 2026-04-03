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
