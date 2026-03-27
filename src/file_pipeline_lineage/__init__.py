"""file_pipeline_lineage — lineage capture for file-based data pipeline runs."""

from file_pipeline_lineage.context import ReplayContext, RunContext
from file_pipeline_lineage.exceptions import (
    LineageError,
    MissingCommitError,
    MissingInputError,
    RunNotFoundError,
)
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.store import LineageStore
from file_pipeline_lineage.tracker import Tracker

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


class Replayer:
    """Loads a LineageRecord and re-executes the captured pipeline. (stub)"""

    def __init__(self, store, replay_root):
        raise NotImplementedError

    def replay(self, run_id: str):
        raise NotImplementedError
