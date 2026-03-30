"""Property-based tests for LineageRecord serialisation."""

from __future__ import annotations

import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.descriptors import InputDescriptor, OutputDescriptor
from file_pipeline_lineage.record import LineageRecord


# ---------------------------------------------------------------------------
# Descriptor strategies
# ---------------------------------------------------------------------------

@st.composite
def input_descriptor_strategy(draw) -> InputDescriptor:
    """Generate valid InputDescriptor instances."""
    return InputDescriptor(
        name=draw(st.text(min_size=1, max_size=60, alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="_:/(). ",
        ))),
        connection_class=draw(st.from_regex(
            r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*:[A-Z][a-zA-Z0-9_]*",
            fullmatch=True,
        )),
        connection_args=draw(st.fixed_dictionaries({
            "path": st.text(min_size=1, max_size=50),
        })),
        access_timestamp=draw(
            st.datetimes(timezones=st.just(datetime.timezone.utc)).map(
                lambda dt: dt.isoformat()
            )
        ),
        time_travel=draw(st.booleans()),
    )


@st.composite
def output_descriptor_strategy(draw) -> OutputDescriptor:
    """Generate valid OutputDescriptor instances."""
    return OutputDescriptor(
        name=draw(st.text(min_size=1, max_size=60, alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="_:/(). ",
        ))),
        connection_class=draw(st.from_regex(
            r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*:[A-Z][a-zA-Z0-9_]*",
            fullmatch=True,
        )),
        connection_args=draw(st.fixed_dictionaries({
            "path": st.text(min_size=1, max_size=50),
        })),
        overwrite_requested=draw(st.booleans()),
        overwrite_status=draw(st.sampled_from([
            "overwrite", "no_overwrite", "unknown", "in_progress"
        ])),
    )


# ---------------------------------------------------------------------------
# LineageRecord strategy
# ---------------------------------------------------------------------------

@st.composite
def lineage_record_strategy(draw) -> LineageRecord:
    """Generate valid LineageRecord instances with descriptor fields."""
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
        inputs=draw(
            st.lists(input_descriptor_strategy(), min_size=0, max_size=5).map(tuple)
        ),
        outputs=draw(
            st.lists(output_descriptor_strategy(), min_size=0, max_size=5).map(tuple)
        ),
        status=draw(st.sampled_from(["success", "failed"])),
        exception_message=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        original_run_id=draw(st.one_of(st.none(), st.uuids().map(str))),
    )


# ---------------------------------------------------------------------------
# Property 1: LineageRecord round-trip
# Feature: generalised-connections, Property 1: LineageRecord round-trip
# ---------------------------------------------------------------------------

# Feature: generalised-connections, Property 1: LineageRecord round-trip
@given(record=lineage_record_strategy())
@settings(max_examples=200)
def test_lineage_record_round_trip(record: LineageRecord) -> None:
    """to_dict() followed by from_dict() must reproduce the original record exactly.

    Validates: Requirements 9.4, 9.5
    """
    restored = LineageRecord.from_dict(record.to_dict())
    assert restored == record
