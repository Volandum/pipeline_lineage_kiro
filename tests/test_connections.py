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
