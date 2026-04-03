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
