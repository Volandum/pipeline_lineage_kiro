"""Exceptions for file_pipeline_lineage."""


class LineageError(Exception):
    """Base exception for all file_pipeline_lineage errors."""


class RunNotFoundError(LineageError):
    """Raised when a requested Run_ID does not exist in the LineageStore."""


class MissingInputError(LineageError):
    """Raised when one or more input files referenced in a LineageRecord are absent."""


class MissingCommitError(LineageError):
    """Raised when the recorded git commit does not exist in the repository."""
