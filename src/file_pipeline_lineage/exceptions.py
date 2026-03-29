"""Exceptions for file_pipeline_lineage."""


class LineageError(Exception):
    """Base exception for all file_pipeline_lineage errors."""


class RunNotFoundError(LineageError):
    """Raised when a requested Run_ID does not exist in the LineageStore."""


class MissingInputError(LineageError):
    """Raised when one or more input files referenced in a LineageRecord are absent."""


class MissingCommitError(LineageError):
    """Raised when the recorded git commit does not exist in the repository."""


class UnsupportedOperationError(LineageError):
    """Raised when a Connection is asked to perform an operation it does not support."""


class TimeTravelError(LineageError):
    """Raised when a time-travel read cannot be satisfied (e.g. no version at the requested timestamp)."""


class ConflictError(LineageError):
    """Raised when a conflict-free write would produce an output address that already exists."""


class ConfigurationError(LineageError):
    """Raised when a Connection is misconfigured or cannot be reconstructed."""


class DuplicateNameError(LineageError):
    """Raised when open_input or open_output is called with a name already in use within the same run."""
