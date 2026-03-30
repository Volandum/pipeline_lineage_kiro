"""LineageRecord dataclass — the central data model for file_pipeline_lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from file_pipeline_lineage.descriptors import InputDescriptor, OutputDescriptor


@dataclass(frozen=True)
class LineageRecord:
    """Immutable record capturing full lineage metadata for a single pipeline run."""

    run_id: str                              # UUID4 string
    timestamp_utc: str                       # ISO-8601 UTC, e.g. "2024-01-15T10:30:00.123456+00:00"
    function_name: str                       # Name of the pipeline function
    git_commit: str                          # Full SHA of HEAD at the time track() was called
    function_ref: str                        # Fully-qualified reference, e.g. "mypackage.pipelines:transform"
    inputs: tuple[InputDescriptor, ...]      # Ordered list of input descriptors
    outputs: tuple[OutputDescriptor, ...]    # Ordered list of output descriptors
    status: str                              # "success" | "failed"
    exception_message: str | None            # None on success; str on failure
    original_run_id: str | None              # None for original runs; set for replay runs

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict; descriptor tuples become JSON arrays of objects."""
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "function_name": self.function_name,
            "git_commit": self.git_commit,
            "function_ref": self.function_ref,
            "inputs": [d.to_dict() for d in self.inputs],
            "outputs": [d.to_dict() for d in self.outputs],
            "status": self.status,
            "exception_message": self.exception_message,
            "original_run_id": self.original_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LineageRecord":
        """Deserialise from a dict; reconstruct descriptor objects from nested dicts."""
        return cls(
            run_id=d["run_id"],
            timestamp_utc=d["timestamp_utc"],
            function_name=d["function_name"],
            git_commit=d["git_commit"],
            function_ref=d["function_ref"],
            inputs=tuple(InputDescriptor.from_dict(i) for i in d.get("inputs", [])),
            outputs=tuple(OutputDescriptor.from_dict(o) for o in d.get("outputs", [])),
            status=d["status"],
            exception_message=d.get("exception_message"),
            original_run_id=d.get("original_run_id"),
        )
