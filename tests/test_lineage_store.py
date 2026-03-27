"""Property-based tests for LineageStore (Properties 4–7)."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.exceptions import LineageError, RunNotFoundError
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.store import LineageStore


# ---------------------------------------------------------------------------
# Shared composite strategy
# ---------------------------------------------------------------------------

@st.composite
def lineage_record(draw) -> LineageRecord:
    """Generate valid LineageRecord instances."""
    return LineageRecord(
        run_id=draw(st.uuids().map(str)),
        timestamp_utc=draw(
            st.datetimes(timezones=st.just(datetime.timezone.utc)).map(
                lambda dt: dt.isoformat()
            )
        ),
        function_name=draw(
            st.text(
                min_size=1,
                max_size=40,
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu", "Nd"),
                    whitelist_characters="_",
                ),
            )
        ),
        git_commit=draw(
            st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)
        ),
        function_ref=draw(
            st.from_regex(
                r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*:[a-z][a-z0-9_]*",
                fullmatch=True,
            )
        ),
        input_paths=draw(
            st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5).map(
                tuple
            )
        ),
        output_paths=draw(
            st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5).map(
                tuple
            )
        ),
        status=draw(st.sampled_from(["success", "failed"])),
        exception_message=draw(
            st.one_of(st.none(), st.text(min_size=1, max_size=100))
        ),
        original_run_id=draw(st.one_of(st.none(), st.uuids().map(str))),
    )


# ---------------------------------------------------------------------------
# Property 4: LineageStore save/load round-trip
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 4: LineageStore save/load round-trip
@given(record=lineage_record())
@settings(max_examples=200)
def test_store_round_trip(record):
    """Validates: Requirements 2.1, 2.4"""
    with tempfile.TemporaryDirectory() as d:
        store = LineageStore(Path(d))
        store.save(record)
        loaded = store.load(record.run_id)
        assert loaded == record


# ---------------------------------------------------------------------------
# Property 5: Distinct Run_IDs get distinct storage paths
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 5: Distinct Run_IDs get distinct storage paths
@given(r1=lineage_record(), r2=lineage_record())
@settings(max_examples=200)
def test_distinct_run_ids_distinct_paths(r1, r2):
    """Validates: Requirements 2.2, 7.2"""
    assume(r1.run_id != r2.run_id)
    with tempfile.TemporaryDirectory() as d:
        store = LineageStore(Path(d))
        p1 = store.save(r1)
        p2 = store.save(r2)
        assert p1 != p2


# ---------------------------------------------------------------------------
# Property 6: Missing Run_ID raises RunNotFoundError
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 6: Missing Run_ID raises RunNotFoundError
@given(run_id=st.uuids().map(str))
@settings(max_examples=200)
def test_missing_run_id_raises(run_id):
    """Validates: Requirements 2.5"""
    with tempfile.TemporaryDirectory() as d:
        store = LineageStore(Path(d))
        with pytest.raises(RunNotFoundError, match=run_id):
            store.load(run_id)


# ---------------------------------------------------------------------------
# Property 7: list_run_ids returns exactly the saved Run_IDs
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 7: list_run_ids returns exactly the saved Run_IDs
@given(records=st.lists(lineage_record(), min_size=0, max_size=10))
@settings(max_examples=200)
def test_list_run_ids_completeness(records):
    """Validates: Requirements 2.6"""
    # Deduplicate by run_id to avoid collisions
    seen = {}
    for r in records:
        seen[r.run_id] = r
    unique_records = list(seen.values())
    with tempfile.TemporaryDirectory() as d:
        store = LineageStore(Path(d))
        for r in unique_records:
            store.save(r)
        expected = sorted(r.run_id for r in unique_records)
        assert store.list_run_ids() == expected


# ---------------------------------------------------------------------------
# Unit tests: error conditions
# ---------------------------------------------------------------------------

def test_run_not_found_error_message_contains_run_id(tmp_path):
    """RunNotFoundError message must contain the missing run_id. Req 2.5"""
    store = LineageStore(tmp_path)
    missing_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    with pytest.raises(RunNotFoundError) as exc_info:
        store.load(missing_id)
    assert missing_id in str(exc_info.value)


def test_corrupt_json_raises_lineage_error(tmp_path):
    """Corrupt JSON in store raises LineageError wrapping JSONDecodeError. Req 2.5"""
    store = LineageStore(tmp_path)
    run_id = "aaaaaaaa-bbbb-4ccc-8ddd-ffffffffffff"
    (tmp_path / f"{run_id}.json").write_text("not valid json", encoding="utf-8")
    with pytest.raises(LineageError, match=run_id):
        store.load(run_id)
