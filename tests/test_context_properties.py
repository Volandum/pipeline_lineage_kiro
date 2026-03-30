"""Property-based tests for RunContext and ReplayContext (Properties 2, 3, 4, 5).

Uses in-memory stub Connection implementations — no real files are touched.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from file_pipeline_lineage.connections import (
    Connection,
    OverwriteStatus,
    WriteResult,
)
from file_pipeline_lineage.context import ReplayContext, RunContext
from file_pipeline_lineage.descriptors import InputDescriptor


# ---------------------------------------------------------------------------
# Stub Connection implementations
# ---------------------------------------------------------------------------

class StubReadConnection(Connection):
    """In-memory connection that supports read() only."""

    def __init__(self, key: str, value: str = "data") -> None:
        self.key = key
        self.value = value
        self._read_calls: list[str | None] = []

    def read(self, timestamp_utc: str | None = None):
        self._read_calls.append(timestamp_utc)
        return self.value

    def serialise(self) -> dict:
        return {"key": self.key, "value": self.value}

    @property
    def supports_time_travel(self) -> bool:
        return False


class StubTimeTravelConnection(Connection):
    """In-memory connection that supports read() with time travel."""

    def __init__(self, key: str, value: str = "data") -> None:
        self.key = key
        self.value = value
        self._read_calls: list[str | None] = []

    def read(self, timestamp_utc: str | None = None):
        self._read_calls.append(timestamp_utc)
        return self.value

    def serialise(self) -> dict:
        return {"key": self.key, "value": self.value}

    @property
    def supports_time_travel(self) -> bool:
        return True


class StubWriteConnection(Connection):
    """In-memory connection that supports write() via a context manager."""

    def __init__(self, key: str) -> None:
        self.key = key
        self._written: list[Any] = []
        self.result: WriteResult | None = None

    def write(self, run_id: str, overwrite: bool = False):
        conn = self

        @contextmanager
        def _ctx():
            yield conn._written
            conn.result = WriteResult(
                OverwriteStatus.OVERWRITE if overwrite else OverwriteStatus.NO_OVERWRITE
            )

        ctx = _ctx()
        # Attach result attribute so RunContext can read it after __exit__
        ctx_obj = ctx
        return ctx_obj

    def serialise(self) -> dict:
        return {"key": self.key}


class StubAtomicReadConnection(Connection):
    """In-memory connection that supports atomic_read() only."""

    def __init__(self, key: str, value: str = "data") -> None:
        self.key = key
        self.value = value
        self._read_calls: list[str | None] = []

    def atomic_read(self, timestamp_utc: str | None = None):
        self._read_calls.append(timestamp_utc)
        return self.value

    def serialise(self) -> dict:
        return {"key": self.key, "value": self.value}

    @property
    def supports_time_travel(self) -> bool:
        return False


class StubTimeTravelAtomicReadConnection(Connection):
    """In-memory connection that supports atomic_read() with time travel."""

    def __init__(self, key: str, value: str = "data") -> None:
        self.key = key
        self.value = value
        self._read_calls: list[str | None] = []

    def atomic_read(self, timestamp_utc: str | None = None):
        self._read_calls.append(timestamp_utc)
        return self.value

    def serialise(self) -> dict:
        return {"key": self.key, "value": self.value}

    @property
    def supports_time_travel(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
)

_run_id_st = st.uuids().map(str)


@st.composite
def stub_read_connections(draw) -> StubReadConnection:
    key = draw(_safe_text)
    value = draw(_safe_text)
    return StubReadConnection(key=key, value=value)


@st.composite
def stub_write_connections(draw) -> StubWriteConnection:
    key = draw(_safe_text)
    return StubWriteConnection(key=key)


@st.composite
def connection_sequences(draw, min_size=1, max_size=5):
    """Generate a list of StubReadConnection instances with distinct keys."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    keys = draw(st.lists(
        _safe_text,
        min_size=n,
        max_size=n,
        unique=True,
    ))
    return [StubReadConnection(key=k) for k in keys]


@st.composite
def output_connection_sequences(draw, min_size=1, max_size=5):
    """Generate a list of StubWriteConnection instances with distinct keys."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    keys = draw(st.lists(
        _safe_text,
        min_size=n,
        max_size=n,
        unique=True,
    ))
    return [StubWriteConnection(key=k) for k in keys]


# ---------------------------------------------------------------------------
# Property 4: Auto-generated name format
# Feature: generalised-connections, Property 4: Auto-generated name format
# ---------------------------------------------------------------------------

@given(
    run_id=_run_id_st,
    connections=connection_sequences(min_size=1, max_size=6),
)
@settings(max_examples=200)
def test_auto_generated_input_name_format(run_id, connections):
    """Validates: Requirements 6.1, 6.2

    For any sequence of open_input calls without explicit names, each
    auto-generated name matches <index>:<ClassName>(...) and no two names
    within the same run are equal.
    """
    ctx = RunContext(run_id=run_id, base_output_dir=".")
    names = []
    for conn in connections:
        ctx.open_input(conn)
    names = [d.name for d in ctx.inputs]

    # All names must be unique
    assert len(names) == len(set(names))

    # Each name must match the pattern <index>:<ClassName>(...)
    pattern = re.compile(r"^\d+:[A-Za-z_][A-Za-z0-9_]*\(.*\)$")
    for i, name in enumerate(names):
        assert pattern.match(name), f"Name {name!r} does not match expected pattern"
        # Index must be 1-based
        idx_str = name.split(":")[0]
        assert int(idx_str) == i + 1

    # Params portion must be at most 50 chars (extract between first '(' and last ')')
    for name in names:
        paren_open = name.index("(")
        paren_close = name.rindex(")")
        params_portion = name[paren_open + 1:paren_close]
        assert len(params_portion) <= 53, (
            f"Params portion {params_portion!r} exceeds 50 chars + '...'"
        )


@given(
    run_id=_run_id_st,
    connections=output_connection_sequences(min_size=1, max_size=6),
)
@settings(max_examples=200)
def test_auto_generated_output_name_format(run_id, connections):
    """Validates: Requirements 6.1, 6.2

    For any sequence of open_output calls without explicit names, each
    auto-generated name matches <index>:<ClassName>(...) and no two names
    within the same run are equal.
    """
    ctx = RunContext(run_id=run_id, base_output_dir=".")
    for conn in connections:
        with ctx.open_output(conn):
            pass

    names = [d.name for d in ctx.outputs]

    # All names must be unique
    assert len(names) == len(set(names))

    # Each name must match the pattern <index>:<ClassName>(...)
    pattern = re.compile(r"^\d+:[A-Za-z_][A-Za-z0-9_]*\(.*\)$")
    for i, name in enumerate(names):
        assert pattern.match(name), f"Name {name!r} does not match expected pattern"
        idx_str = name.split(":")[0]
        assert int(idx_str) == i + 1


# ---------------------------------------------------------------------------
# Property 2: Input descriptor completeness
# Feature: generalised-connections, Property 2: Input descriptor completeness
# ---------------------------------------------------------------------------

_ISO_8601_UTC = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"  # date and time
    r"(\.\d+)?"                                 # optional fractional seconds
    r"(\+00:00|Z)$"                             # UTC offset
)


def _is_valid_iso8601_utc(ts: str) -> bool:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0
    except ValueError:
        return False


@given(
    run_id=_run_id_st,
    conn=stub_read_connections(),
)
@settings(max_examples=200)
def test_input_descriptor_completeness_open_input(run_id, conn):
    """Validates: Requirements 5.5, 5.6, 5.9, 9.1, 9.3

    For any Connection passed to ctx.open_input, the recorded descriptor
    contains correct name, connection_class, connection_args matching
    connection.serialise(), valid ISO-8601 UTC access_timestamp, and
    time_travel=False.
    """
    ctx = RunContext(run_id=run_id, base_output_dir=".")
    ctx.open_input(conn)

    assert len(ctx.inputs) == 1
    d = ctx.inputs[0]

    # Name is auto-generated and non-empty
    assert d.name and isinstance(d.name, str)

    # connection_class is fully-qualified
    assert ":" in d.connection_class
    module, qualname = d.connection_class.split(":", 1)
    assert module and qualname

    # connection_args matches serialise()
    assert d.connection_args == conn.serialise()

    # access_timestamp is a valid ISO-8601 UTC string
    assert _is_valid_iso8601_utc(d.access_timestamp), (
        f"access_timestamp {d.access_timestamp!r} is not valid ISO-8601 UTC"
    )

    # time_travel is False for original runs
    assert d.time_travel is False


@given(
    run_id=_run_id_st,
    conn=st.builds(StubAtomicReadConnection, key=_safe_text, value=_safe_text),
)
@settings(max_examples=200)
def test_input_descriptor_completeness_atomic_read(run_id, conn):
    """Validates: Requirements 5.5, 5.6, 5.9, 9.1, 9.3

    Same as open_input but via atomic_read.
    """
    ctx = RunContext(run_id=run_id, base_output_dir=".")
    ctx.atomic_read(conn)

    assert len(ctx.inputs) == 1
    d = ctx.inputs[0]

    assert d.name and isinstance(d.name, str)
    assert ":" in d.connection_class
    assert d.connection_args == conn.serialise()
    assert _is_valid_iso8601_utc(d.access_timestamp)
    assert d.time_travel is False


# ---------------------------------------------------------------------------
# Property 3: Output descriptor completeness
# Feature: generalised-connections, Property 3: Output descriptor completeness
# ---------------------------------------------------------------------------

@given(
    run_id=_run_id_st,
    conn=stub_write_connections(),
    overwrite=st.booleans(),
)
@settings(max_examples=200)
def test_output_descriptor_completeness(run_id, conn, overwrite):
    """Validates: Requirements 5.4, 7.5, 7.6, 7.7, 7.9, 9.2, 9.3

    For any Connection passed to ctx.open_output, after the context manager
    exits, the descriptor has a final overwrite_status (not 'in_progress').
    """
    ctx = RunContext(run_id=run_id, base_output_dir=".")

    # While context manager is open, status should be in_progress
    with ctx.open_output(conn, overwrite=overwrite):
        assert len(ctx.outputs) == 1
        assert ctx.outputs[0].overwrite_status == OverwriteStatus.IN_PROGRESS.value

    # After __exit__, status must be final (not in_progress)
    assert len(ctx.outputs) == 1
    d = ctx.outputs[0]

    assert d.name and isinstance(d.name, str)
    assert ":" in d.connection_class
    assert d.connection_args == conn.serialise()
    assert d.overwrite_requested == overwrite
    assert d.overwrite_status != OverwriteStatus.IN_PROGRESS.value
    assert d.overwrite_status in (
        OverwriteStatus.OVERWRITE.value,
        OverwriteStatus.NO_OVERWRITE.value,
        OverwriteStatus.UNKNOWN.value,
    )


# ---------------------------------------------------------------------------
# Property 5: Time-travel routing
# Feature: generalised-connections, Property 5: Time-travel routing
# ---------------------------------------------------------------------------

@st.composite
def replay_scenario(draw):
    """Generate a list of (connection, supports_time_travel, access_timestamp) tuples."""
    n = draw(st.integers(min_value=1, max_value=5))
    keys = draw(st.lists(_safe_text, min_size=n, max_size=n, unique=True))
    supports_tt = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    timestamps = [
        f"2024-01-{i+1:02d}T10:00:00.000000+00:00" for i in range(n)
    ]
    return list(zip(keys, supports_tt, timestamps))


@given(
    run_id=_run_id_st,
    orig_run_id=_run_id_st,
    scenario=replay_scenario(),
)
@settings(max_examples=200)
def test_time_travel_routing(run_id, orig_run_id, scenario):
    """Validates: Requirements 8.1, 8.2, 8.3, 8.4

    For any ReplayContext, each input with supports_time_travel=True is called
    with access_timestamp; each with False is called with None. Replay
    descriptor records time_travel accordingly.
    """
    # Build original_inputs dict from scenario
    original_inputs: dict[str, InputDescriptor] = {}
    connections: list[Connection] = []

    for key, supports_tt, ts in scenario:
        # Auto-generate the name that ReplayContext will use
        # We need to know the name ahead of time — use explicit names here
        name = f"input_{key}"
        original_inputs[name] = InputDescriptor(
            name=name,
            connection_class="tests.test_context_properties:StubReadConnection",
            connection_args={"key": key, "value": "data"},
            access_timestamp=ts,
            time_travel=False,
        )
        if supports_tt:
            conn = StubTimeTravelConnection(key=key)
        else:
            conn = StubReadConnection(key=key)
        connections.append(conn)

    ctx = ReplayContext(
        run_id=run_id,
        orig_run_id=orig_run_id,
        replay_root=".",
        original_inputs=original_inputs,
    )

    for (key, supports_tt, ts), conn in zip(scenario, connections):
        name = f"input_{key}"
        ctx.open_input(conn, name=name)

    assert len(ctx.inputs) == len(scenario)

    for i, (key, supports_tt, ts) in enumerate(scenario):
        d = ctx.inputs[i]
        conn = connections[i]

        if supports_tt:
            # Should have been called with the recorded access_timestamp
            assert d.time_travel is True
            assert d.access_timestamp == ts
            assert conn._read_calls == [ts]
        else:
            # Should have been called with None (live read)
            assert d.time_travel is False
            assert conn._read_calls == [None]


@given(
    run_id=_run_id_st,
    orig_run_id=_run_id_st,
    scenario=replay_scenario(),
)
@settings(max_examples=200)
def test_time_travel_routing_atomic_read(run_id, orig_run_id, scenario):
    """Validates: Requirements 8.1, 8.2, 8.3, 8.4

    Same as test_time_travel_routing but via atomic_read.
    """
    original_inputs: dict[str, InputDescriptor] = {}
    connections: list[Connection] = []

    for key, supports_tt, ts in scenario:
        name = f"input_{key}"
        original_inputs[name] = InputDescriptor(
            name=name,
            connection_class="tests.test_context_properties:StubAtomicReadConnection",
            connection_args={"key": key, "value": "data"},
            access_timestamp=ts,
            time_travel=False,
        )
        if supports_tt:
            conn = StubTimeTravelAtomicReadConnection(key=key)
        else:
            conn = StubAtomicReadConnection(key=key)
        connections.append(conn)

    ctx = ReplayContext(
        run_id=run_id,
        orig_run_id=orig_run_id,
        replay_root=".",
        original_inputs=original_inputs,
    )

    for (key, supports_tt, ts), conn in zip(scenario, connections):
        name = f"input_{key}"
        ctx.atomic_read(conn, name=name)

    assert len(ctx.inputs) == len(scenario)

    for i, (key, supports_tt, ts) in enumerate(scenario):
        d = ctx.inputs[i]
        conn = connections[i]

        if supports_tt:
            assert d.time_travel is True
            assert d.access_timestamp == ts
            assert conn._read_calls == [ts]
        else:
            assert d.time_travel is False
            assert conn._read_calls == [None]
