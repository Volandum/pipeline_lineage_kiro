"""Replayer — loads a LineageRecord and re-executes the captured pipeline."""

from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from file_pipeline_lineage.context import ReplayContext
from file_pipeline_lineage.exceptions import LineageError, MissingCommitError, MissingInputError
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.store import LineageStore


class Replayer:
    def __init__(self, store: LineageStore, replay_root: str | Path) -> None:
        self._store = store
        self._replay_root = Path(replay_root)

    def replay(self, run_id: str) -> LineageRecord:
        # 1. Load original record
        record = self._store.load(run_id)

        # 2. Validate input files exist
        missing = [p for p in record.input_paths if not Path(p).exists()]
        if missing:
            raise MissingInputError(
                f"Missing input files for run '{run_id}': {missing}"
            )

        # 3. Check git commit exists
        result = subprocess.run(
            ["git", "cat-file", "-e", record.git_commit],
            capture_output=True
        )
        if result.returncode != 0:
            raise MissingCommitError(
                f"Git commit '{record.git_commit}' not found in repository"
            )

        # 4. Create git worktree for the recorded commit
        replay_run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as worktree_dir:
            wt_result = subprocess.run(
                ["git", "worktree", "add", "--detach", worktree_dir, record.git_commit],
                capture_output=True, text=True
            )
            if wt_result.returncode != 0:
                raise LineageError(
                    f"Failed to create git worktree: {wt_result.stderr.strip()}"
                )
            try:
                # 5. Import function from worktree
                sys.path.insert(0, worktree_dir)
                try:
                    module_name, func_name = record.function_ref.split(":", 1)
                    # Invalidate any cached module from a previous replay
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                    module = importlib.import_module(module_name)
                    fn = getattr(module, func_name)
                finally:
                    sys.path.remove(worktree_dir)

                # 6. Execute via ReplayContext
                ctx = ReplayContext(replay_run_id, record.run_id, self._replay_root)
                timestamp_utc = datetime.now(timezone.utc).isoformat()
                try:
                    fn(ctx)
                except Exception as e:
                    replay_record = LineageRecord(
                        run_id=replay_run_id,
                        timestamp_utc=timestamp_utc,
                        function_name=record.function_name,
                        git_commit=record.git_commit,
                        function_ref=record.function_ref,
                        input_paths=ctx.inputs,
                        output_paths=ctx.outputs,
                        status="failed",
                        exception_message=str(e),
                        original_run_id=record.run_id,
                    )
                    self._store.save(replay_record)
                    raise

                replay_record = LineageRecord(
                    run_id=replay_run_id,
                    timestamp_utc=timestamp_utc,
                    function_name=record.function_name,
                    git_commit=record.git_commit,
                    function_ref=record.function_ref,
                    input_paths=ctx.inputs,
                    output_paths=ctx.outputs,
                    status="success",
                    exception_message=None,
                    original_run_id=record.run_id,
                )
                self._store.save(replay_record)
                return replay_record

            finally:
                # 7. Clean up worktree
                subprocess.run(
                    ["git", "worktree", "remove", "--force", worktree_dir],
                    capture_output=True
                )
