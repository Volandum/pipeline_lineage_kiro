"""file_pipeline_lineage — lineage capture for file-based data pipeline runs."""

from file_pipeline_lineage.connections import (
    Connection,
    LocalConnection,
    OverwriteStatus,
    S3Connection,
    WriteResult,
)
from file_pipeline_lineage.context import ReplayContext, RunContext
from file_pipeline_lineage.contract import ConnectionContractTests
from file_pipeline_lineage.exceptions import (
    ConfigurationError,
    ConflictError,
    DuplicateNameError,
    LineageError,
    MissingCommitError,
    MissingInputError,
    RunNotFoundError,
    TimeTravelError,
    UnsupportedOperationError,
)
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.replayer import Replayer
from file_pipeline_lineage.store import LineageStore
from file_pipeline_lineage.tracker import Tracker

__all__ = [
    # Core context
    "RunContext",
    "ReplayContext",
    # Data model
    "LineageRecord",
    "LineageStore",
    # Pipeline execution
    "Tracker",
    "Replayer",
    # Connection interface
    "Connection",
    "LocalConnection",
    "S3Connection",
    "WriteResult",
    "OverwriteStatus",
    "ConnectionContractTests",
    # Exceptions
    "LineageError",
    "RunNotFoundError",
    "MissingInputError",
    "MissingCommitError",
    "UnsupportedOperationError",
    "TimeTravelError",
    "ConflictError",
    "ConfigurationError",
    "DuplicateNameError",
]
