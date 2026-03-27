"""LineageRecord dataclass — the central data model for file_pipeline_lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LineageRecord:
    """Immutable record capturing full lineage metadata for a single pipeline run."""

    run_id: str                    # UUID4 string
    timestamp_utc: str             # ISO-8601 UTC, e.g. "2024-01-15T10:30:00.123456+00:00"
    function_name: str             # Name of the pipeline function
    git_commit: str                # Full SHA of HEAD at the time track() was called
    function_ref: str              # Fully-qualified reference, e.g. "mypackage.pipelines:transform"
    input_paths: tuple[str, ...]   # Paths as provided to ctx.open_input()
    output_paths: tuple[str, ...]  # Resolved paths as constructed by RunContext/ReplayContext
    status: str                    # "success" | "failed"
    exception_message: str | None  # None on success; str on failure
    original_run_id: str | None    # None for original runs; set for replay runs

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict; tuples become lists for JSON compatibility."""
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "function_name": self.function_name,
            "git_commit": self.git_commit,
            "function_ref": self.function_ref,
            "input_paths": list(self.input_paths),
            "output_paths": list(self.output_paths),
            "status": self.status,
            "exception_message": self.exception_message,
            "original_run_id": self.original_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LineageRecord":
        """Deserialise from a dict; list fields are converted back to tuple[str, ...]."""
        return cls(
            run_id=d["run_id"],
            timestamp_utc=d["timestamp_utc"],
            function_name=d["function_name"],
            git_commit=d["git_commit"],
            function_ref=d["function_ref"],
            input_paths=tuple(d["input_paths"]),
            output_paths=tuple(d["output_paths"]),
            status=d["status"],
            exception_message=d.get("exception_message"),
            original_run_id=d.get("original_run_id"),
        )
