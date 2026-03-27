"""Property-based tests for LineageRecord serialisation (Property 4 — serialisation half)."""

from __future__ import annotations

import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.record import LineageRecord


# ---------------------------------------------------------------------------
# Shared composite strategy (mirrors the one in test_lineage_store.py)
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
            st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5).map(tuple)
        ),
        output_paths=draw(
            st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5).map(tuple)
        ),
        status=draw(st.sampled_from(["success", "failed"])),
        exception_message=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        original_run_id=draw(st.one_of(st.none(), st.uuids().map(str))),
    )


# ---------------------------------------------------------------------------
# Property 4 (serialisation half): to_dict / from_dict round-trip
# ---------------------------------------------------------------------------

# Feature: file-pipeline-lineage, Property 4: LineageStore save/load round-trip
@given(record=lineage_record())
@settings(max_examples=200)
def test_lineage_record_serialisation_round_trip(record: LineageRecord) -> None:
    """to_dict() followed by from_dict() must reproduce the original record exactly.

    Validates: Requirements 2.1, 2.4
    """
    restored = LineageRecord.from_dict(record.to_dict())
    assert restored == record
