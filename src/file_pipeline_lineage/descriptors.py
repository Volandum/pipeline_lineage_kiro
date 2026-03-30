"""Descriptor dataclasses for lineage record inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InputDescriptor:
    """Describes a single input connection used in a pipeline run.

    Fields:
        name: Connection name (identity key).
        connection_class: Fully-qualified import path, e.g.
            "file_pipeline_lineage.connections:LocalConnection".
        connection_args: Result of connection.serialise().
        access_timestamp: ISO-8601 UTC string recorded at open time.
        time_travel: False for original runs; True/False for replays.
    """

    name: str
    connection_class: str
    connection_args: dict = field(default_factory=dict)
    access_timestamp: str = ""
    time_travel: bool = False

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "name": self.name,
            "connection_class": self.connection_class,
            "connection_args": self.connection_args,
            "access_timestamp": self.access_timestamp,
            "time_travel": self.time_travel,
        }

    @classmethod
    def from_dict(cls, d: dict) -> InputDescriptor:
        """Reconstruct an InputDescriptor from a plain dict."""
        return cls(
            name=d["name"],
            connection_class=d["connection_class"],
            connection_args=d.get("connection_args", {}),
            access_timestamp=d.get("access_timestamp", ""),
            time_travel=d.get("time_travel", False),
        )


@dataclass
class OutputDescriptor:
    """Describes a single output connection used in a pipeline run.

    Fields:
        name: Connection name (identity key).
        connection_class: Fully-qualified import path.
        connection_args: Result of connection.serialise().
        overwrite_requested: Whether overwrite=True was passed.
        overwrite_status: One of "overwrite", "no_overwrite", "unknown", "in_progress".
        access_start_timestamp: ISO-8601 UTC recorded when the write begins (before __enter__ / atomic_write call).
        access_end_timestamp: ISO-8601 UTC recorded when the write finishes successfully. Empty string on failure or in progress.
    """

    name: str
    connection_class: str
    connection_args: dict = field(default_factory=dict)
    overwrite_requested: bool = False
    overwrite_status: str = "unknown"
    access_start_timestamp: str = ""
    access_end_timestamp: str = ""

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "name": self.name,
            "connection_class": self.connection_class,
            "connection_args": self.connection_args,
            "overwrite_requested": self.overwrite_requested,
            "overwrite_status": self.overwrite_status,
            "access_start_timestamp": self.access_start_timestamp,
            "access_end_timestamp": self.access_end_timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> OutputDescriptor:
        """Reconstruct an OutputDescriptor from a plain dict."""
        return cls(
            name=d["name"],
            connection_class=d["connection_class"],
            connection_args=d.get("connection_args", {}),
            overwrite_requested=d.get("overwrite_requested", False),
            overwrite_status=d.get("overwrite_status", "unknown"),
            access_start_timestamp=d.get("access_start_timestamp", ""),
            access_end_timestamp=d.get("access_end_timestamp", ""),
        )
