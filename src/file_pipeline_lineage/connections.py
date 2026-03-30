"""Connection ABC and built-in connectors for file_pipeline_lineage.

Built-in connectors:
- LocalConnection: fully-supported connector for local filesystem paths.
- S3Connection: reference/example S3 connector — not production-ready.
"""

from __future__ import annotations

import inspect
import os
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import IO

from file_pipeline_lineage.exceptions import (
    ConflictError,
    UnsupportedOperationError,
)


# ---------------------------------------------------------------------------
# WriteResult / OverwriteStatus
# ---------------------------------------------------------------------------

class OverwriteStatus(str, Enum):
    OVERWRITE = "overwrite"
    NO_OVERWRITE = "no_overwrite"
    UNKNOWN = "unknown"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class WriteResult:
    overwrite_status: OverwriteStatus


# ---------------------------------------------------------------------------
# Connection ABC
# ---------------------------------------------------------------------------

class Connection(ABC):
    """Abstract base class for all data source/sink connectors.

    No abstract methods — connectors opt in by subclassing and implementing
    only the methods their backing store supports. Unimplemented methods raise
    UnsupportedOperationError by default.
    """

    def read(self, timestamp_utc: str | None = None):
        """Streaming read. Return type not prescribed — passed directly to user code.

        timestamp_utc=None → live read; ISO-8601 UTC string → time-travel read.
        """
        raise UnsupportedOperationError(f"{type(self).__name__} does not support read()")

    def atomic_read(self, timestamp_utc: str | None = None):
        """Read and return all data at once. Return type not prescribed."""
        raise UnsupportedOperationError(
            f"{type(self).__name__} does not support atomic_read()"
        )

    def write(self, run_id: str, overwrite: bool = False):
        """Returns a context manager. WriteResult | None available after __exit__ completes.

        run_id is incorporated into the output address for per-run isolation.
        """
        raise UnsupportedOperationError(f"{type(self).__name__} does not support write()")

    def atomic_write(self, data, run_id: str, overwrite: bool = False):
        """Write data atomically. Returns WriteResult | None.

        None means the connection cannot determine overwrite status.
        """
        raise UnsupportedOperationError(
            f"{type(self).__name__} does not support atomic_write()"
        )

    def serialise(self) -> dict:
        """Return a JSON-serialisable dict of non-secret constructor args.

        Default implementation uses inspect.signature; override to exclude secrets
        or rename fields.
        """
        sig = inspect.signature(self.__init__)
        return {
            name: getattr(self, name)
            for name in sig.parameters
            if name != "self"
        }

    @property
    def supports_time_travel(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# LocalConnection
# ---------------------------------------------------------------------------

class _LocalWriteContext:
    """Context manager returned by LocalConnection.write()."""

    def __init__(
        self,
        output_path: Path,
        overwrite: bool,
    ) -> None:
        self._output_path = output_path
        self._overwrite = overwrite
        self._existed_before: bool = False
        self._file: IO | None = None
        self.result: WriteResult | None = None

    def __enter__(self) -> IO:
        self._existed_before = self._output_path.exists()
        if not self._overwrite and self._existed_before:
            raise ConflictError(
                f"Output path already exists and overwrite=False: {self._output_path}"
            )
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._output_path, "w")  # noqa: SIM115
        return self._file

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file is not None:
            self._file.close()
        if exc_type is None:
            # Success: set final WriteResult
            status = (
                OverwriteStatus.OVERWRITE
                if self._existed_before
                else OverwriteStatus.NO_OVERWRITE
            )
            self.result = WriteResult(status)
        else:
            # Exception: remove partial file
            if self._output_path.exists():
                try:
                    os.remove(self._output_path)
                except OSError:
                    pass
            # result stays None — caller records IN_PROGRESS
        return False  # do not suppress exceptions


class LocalConnection(Connection):
    """Fully-supported built-in connector for local filesystem paths."""

    def __init__(
        self,
        path: str | Path,
        base_output_dir: str | Path | None = None,
    ) -> None:
        self.path = path
        self.base_output_dir = base_output_dir

    def read(self, timestamp_utc: str | None = None) -> IO:
        """Open path for reading. Raises UnsupportedOperationError if timestamp_utc is not None."""
        if timestamp_utc is not None:
            raise UnsupportedOperationError(
                f"LocalConnection does not support time-travel reads "
                f"(timestamp_utc={timestamp_utc!r})"
            )
        return open(self.path, "r")  # noqa: SIM115

    def write(self, run_id: str, overwrite: bool = False) -> _LocalWriteContext:
        """Return a context manager that writes to <base_output_dir>/<run_id>/<filename>."""
        base = Path(self.base_output_dir) if self.base_output_dir is not None else Path(".")
        filename = Path(self.path).name
        output_path = base / run_id / filename
        return _LocalWriteContext(output_path, overwrite)

    def atomic_read(self, timestamp_utc: str | None = None):
        raise UnsupportedOperationError("LocalConnection does not support atomic_read()")

    def atomic_write(self, data, run_id: str, overwrite: bool = False):
        raise UnsupportedOperationError("LocalConnection does not support atomic_write()")

    def serialise(self) -> dict:
        """Return {"path": "<absolute path string>"}."""
        return {"path": str(Path(self.path).resolve())}

    @property
    def supports_time_travel(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# S3Connection (reference — not production-ready)
# ---------------------------------------------------------------------------

"""Reference/example S3 connector — not production-ready."""


class S3Connection(Connection):
    """Reference/example S3 connector — not production-ready.

    Implements read (streaming download, with optional time-travel via S3 Object
    Versioning) and atomic_write (single PUT). Does NOT implement write (streaming
    context manager) or atomic_read — calling either raises UnsupportedOperationError.

    boto3 is an optional dependency; it is imported lazily inside methods so this
    class can be imported without boto3 installed. Methods raise ImportError if
    boto3 is missing at call time.
    """

    def __init__(self, bucket: str, key: str, time_travel: bool = False) -> None:
        self.bucket = bucket
        self.key = key
        self.time_travel = time_travel

    def read(self, timestamp_utc: str | None = None):
        """Streaming download from S3.

        If timestamp_utc is None, downloads the current object.
        If timestamp_utc is not None and self.time_travel is False, raises
        UnsupportedOperationError.
        If timestamp_utc is not None and self.time_travel is True, retrieves the
        S3 object version whose LastModified is the latest at or before timestamp_utc.
        Raises TimeTravelError if no such version exists.
        Raises ConfigurationError if versioning is not enabled on the bucket.
        """
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3Connection.read(). "
                "Install it with: pip install boto3"
            ) from exc

        from io import BytesIO

        from file_pipeline_lineage.exceptions import ConfigurationError, TimeTravelError

        s3 = boto3.client("s3")

        if timestamp_utc is None:
            buf = BytesIO()
            s3.download_fileobj(self.bucket, self.key, buf)
            buf.seek(0)
            return buf

        # Time-travel read
        if not self.time_travel:
            raise UnsupportedOperationError(
                f"S3Connection(bucket={self.bucket!r}, key={self.key!r}) does not "
                f"support time-travel reads (time_travel=False). "
                f"Requested timestamp: {timestamp_utc!r}"
            )

        # Check versioning status
        versioning = s3.get_bucket_versioning(Bucket=self.bucket)
        status = versioning.get("Status", "")
        if status != "Enabled":
            raise ConfigurationError(
                f"S3 bucket {self.bucket!r} does not have versioning enabled. "
                "Enable versioning to use time-travel reads."
            )

        from datetime import datetime, timezone

        target_dt = datetime.fromisoformat(timestamp_utc)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)

        # List all versions and find the latest at or before target_dt
        paginator = s3.get_paginator("list_object_versions")
        best_version_id = None
        best_last_modified = None

        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.key):
            for version in page.get("Versions", []):
                if version.get("Key") != self.key:
                    continue
                last_modified = version["LastModified"]
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                if last_modified <= target_dt:
                    if best_last_modified is None or last_modified > best_last_modified:
                        best_last_modified = last_modified
                        best_version_id = version["VersionId"]

        if best_version_id is None:
            raise TimeTravelError(
                f"No S3 version of s3://{self.bucket}/{self.key} exists at or before "
                f"{timestamp_utc!r}."
            )

        buf = BytesIO()
        s3.download_fileobj(
            self.bucket, self.key, buf, ExtraArgs={"VersionId": best_version_id}
        )
        buf.seek(0)
        return buf

    def atomic_write(self, data, run_id: str, overwrite: bool = False) -> WriteResult:
        """Upload data to <run_id>/<key_filename> via a single PUT.

        Returns WriteResult with OVERWRITE or NO_OVERWRITE based on whether the
        key existed before upload.
        """
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3Connection.atomic_write(). "
                "Install it with: pip install boto3"
            ) from exc

        from io import BytesIO

        s3 = boto3.client("s3")
        key_filename = Path(self.key).name
        dest_key = f"{run_id}/{key_filename}"

        # Check if key already exists
        existed = False
        try:
            s3.head_object(Bucket=self.bucket, Key=dest_key)
            existed = True
        except s3.exceptions.ClientError:
            pass

        payload = data if isinstance(data, (bytes, BytesIO)) else data
        s3.put_object(Bucket=self.bucket, Key=dest_key, Body=payload)

        return WriteResult(
            OverwriteStatus.OVERWRITE if existed else OverwriteStatus.NO_OVERWRITE
        )

    def write(self, run_id: str, overwrite: bool = False):
        raise UnsupportedOperationError(
            "S3Connection does not support streaming write(). Use atomic_write() instead."
        )

    def atomic_read(self, timestamp_utc: str | None = None):
        raise UnsupportedOperationError(
            "S3Connection does not support atomic_read(). Use read() instead."
        )

    def serialise(self) -> dict:
        """Return {"bucket": ..., "key": ..., "time_travel": bool}. No credentials."""
        return {
            "bucket": self.bucket,
            "key": self.key,
            "time_travel": self.time_travel,
        }

    @property
    def supports_time_travel(self) -> bool:
        return self.time_travel
