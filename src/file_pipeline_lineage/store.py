"""LineageStore — atomic JSON persistence for LineageRecord objects."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from file_pipeline_lineage.exceptions import LineageError, RunNotFoundError
from file_pipeline_lineage.record import LineageRecord


class LineageStore:
    """Persists and retrieves LineageRecords as JSON files on disk."""

    def __init__(self, store_root: str | Path) -> None:
        self._root = Path(store_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, record: LineageRecord) -> Path:
        """Atomically write record as JSON. Returns the path written."""
        target = self._root / f"{record.run_id}.json"
        data = json.dumps(record.to_dict(), indent=2).encode()
        with tempfile.NamedTemporaryFile(
            dir=self._root, delete=False, suffix=".tmp"
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, target)
        return target

    def load(self, run_id: str) -> LineageRecord:
        """Load and deserialise record. Raises RunNotFoundError if absent."""
        target = self._root / f"{run_id}.json"
        if not target.exists():
            raise RunNotFoundError(f"Run '{run_id}' not found in store")
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise LineageError(f"Corrupt record for run '{run_id}': {e}") from e
        return LineageRecord.from_dict(data)

    def list_run_ids(self) -> list[str]:
        """Return all stored Run_IDs sorted by filename."""
        return [p.stem for p in sorted(self._root.glob("*.json"))]
