"""Tracker — wraps pipeline execution and captures full lineage."""

from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from file_pipeline_lineage.context import RunContext
from file_pipeline_lineage.exceptions import LineageError
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.store import LineageStore


class Tracker:
    """Wraps a pipeline function call, assigns a Run_ID, and persists a LineageRecord."""

    def __init__(self, store: LineageStore) -> None:
        self._store = store

    def track(self, fn: Callable[[RunContext], None], base_output_dir: str | Path) -> LineageRecord:
        """Execute fn(ctx), capture lineage, persist record, and return it.

        On exception: records failed status + ctx.outputs at exception time, re-raises.
        """
        # 1. Capture git commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise LineageError(f"Failed to get git commit: {result.stderr.strip()}")
        git_commit = result.stdout.strip()

        # 2. Assign run_id and timestamp
        run_id = str(uuid.uuid4())
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # 3. Derive function_ref as "module:qualname"
        function_name = fn.__name__
        function_ref = f"{fn.__module__}:{fn.__qualname__}"

        # 4. Create RunContext and execute
        ctx = RunContext(run_id, base_output_dir)
        try:
            fn(ctx)
        except Exception as e:
            record = LineageRecord(
                run_id=run_id,
                timestamp_utc=timestamp_utc,
                function_name=function_name,
                git_commit=git_commit,
                function_ref=function_ref,
                inputs=ctx.inputs,
                outputs=ctx.outputs,
                status="failed",
                exception_message=str(e),
                original_run_id=None,
            )
            self._store.save(record)
            raise

        # 5. Success path
        record = LineageRecord(
            run_id=run_id,
            timestamp_utc=timestamp_utc,
            function_name=function_name,
            git_commit=git_commit,
            function_ref=function_ref,
            inputs=ctx.inputs,
            outputs=ctx.outputs,
            status="success",
            exception_message=None,
            original_run_id=None,
        )
        self._store.save(record)
        return record
