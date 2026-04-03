"""demo/pipeline.py — pipeline module for the demo notebook."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from file_pipeline_lineage import Connection, OverwriteStatus, UnsupportedOperationError, WriteResult

# Set by the notebook before Tracker.track() is called.
DB_PATH: str = ""


class SimulatedDBConnection(Connection):
    """Reads from a local SQLite file; simulates a DB source for the demo."""

    supports_time_travel = False

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def atomic_read(self, timestamp_utc=None) -> pd.DataFrame:
        if timestamp_utc is not None:
            raise UnsupportedOperationError(
                "SimulatedDBConnection does not support time-travel reads."
            )
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query("SELECT * FROM records", conn)

    def serialise(self) -> dict:
        return {"db_path": str(self.db_path)}


class MockS3Connection(Connection):
    """Wraps S3Connection behaviour with an in-memory store; no real boto3 calls."""

    supports_time_travel = False

    def __init__(self, bucket: str, key: str, time_travel: bool = False) -> None:
        self.bucket = bucket
        self.key = key
        self.time_travel = time_travel

        self._store: dict = {}

        mock_client = MagicMock()

        def _head_object(**kwargs):
            k = kwargs.get("Key", "")
            if k not in self._store:
                raise mock_client.exceptions.ClientError()
            return {}

        def _put_object(**kwargs):
            self._store[kwargs["Key"]] = kwargs["Body"]

        mock_client.head_object.side_effect = _head_object
        mock_client.put_object.side_effect = _put_object
        self._mock_client = mock_client

    def atomic_write(self, data, run_id: str, overwrite: bool = False) -> WriteResult:
        dest_key = f"{run_id}/{Path(self.key).name}"
        existed = dest_key in self._store
        self._store[dest_key] = data
        return WriteResult(OverwriteStatus.OVERWRITE if existed else OverwriteStatus.NO_OVERWRITE)

    def serialise(self) -> dict:
        return {"bucket": self.bucket, "key": self.key, "time_travel": self.time_travel}
