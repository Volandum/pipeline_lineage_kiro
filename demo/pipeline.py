"""demo/pipeline.py — pipeline module for the demo notebook."""

import sqlite3

import pandas as pd

from file_pipeline_lineage import Connection, UnsupportedOperationError

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
