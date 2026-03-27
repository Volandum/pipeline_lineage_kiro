"""file_pipeline_lineage — lineage capture for file-based data pipeline runs."""

from file_pipeline_lineage.exceptions import (
    LineageError,
    MissingCommitError,
    MissingInputError,
    RunNotFoundError,
)
from file_pipeline_lineage.record import LineageRecord

__all__ = [
    "RunContext",
    "ReplayContext",
    "LineageRecord",
    "LineageStore",
    "Tracker",
    "Replayer",
    "LineageError",
    "RunNotFoundError",
    "MissingInputError",
    "MissingCommitError",
]


class RunContext:
    """I/O interception object passed to every pipeline function. (stub)"""

    def open_input(self, path, mode="r", **kwargs):
        raise NotImplementedError

    def open_output(self, path, mode="w", **kwargs):
        raise NotImplementedError

    @property
    def run_id(self) -> str:
        raise NotImplementedError

    @property
    def inputs(self) -> tuple:
        raise NotImplementedError

    @property
    def outputs(self) -> tuple:
        raise NotImplementedError


class ReplayContext(RunContext):
    """RunContext specialisation used by the Replayer. (stub)"""

    def open_output(self, path, mode="w", **kwargs):
        raise NotImplementedError


class LineageStore:
    """Persists and retrieves LineageRecords as JSON files on disk. (stub)"""

    def __init__(self, store_root):
        raise NotImplementedError

    def save(self, record):
        raise NotImplementedError

    def load(self, run_id: str):
        raise NotImplementedError

    def list_run_ids(self) -> list:
        raise NotImplementedError


class Tracker:
    """Wraps pipeline execution and captures lineage. (stub)"""

    def __init__(self, store):
        raise NotImplementedError

    def track(self, fn, base_output_dir):
        raise NotImplementedError


class Replayer:
    """Loads a LineageRecord and re-executes the captured pipeline. (stub)"""

    def __init__(self, store, replay_root):
        raise NotImplementedError

    def replay(self, run_id: str):
        raise NotImplementedError
