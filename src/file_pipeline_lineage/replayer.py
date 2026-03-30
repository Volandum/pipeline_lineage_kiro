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
from file_pipeline_lineage.descriptors import InputDescriptor
from file_pipeline_lineage.exceptions import (
    ConfigurationError,
    LineageError,
    MissingCommitError,
)
from file_pipeline_lineage.record import LineageRecord
from file_pipeline_lineage.store import LineageStore


def _reconstruct_connection(descriptor: InputDescriptor):
    """Reconstruct a Connection from a stored descriptor using importlib.

    Raises ConfigurationError if the class cannot be imported or instantiated.
    """
    try:
        module_path, class_name = descriptor.connection_class.split(":", 1)
        cls = getattr(importlib.import_module(module_path), class_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise ConfigurationError(
            f"Cannot import connection class '{descriptor.connection_class}' "
            f"for input '{descriptor.name}': {exc}"
        ) from exc

    try:
        return cls(**descriptor.connection_args)
    except Exception as exc:
        raise ConfigurationError(
            f"Cannot reconstruct connection '{descriptor.name}' "
            f"from class '{descriptor.connection_class}' "
            f"with args {descriptor.connection_args!r}: {exc}"
        ) from exc


class Replayer:
    def __init__(self, store: LineageStore, replay_root: str | Path) -> None:
        self._store = store
        self._replay_root = Path(replay_root)

    def replay(self, run_id: str) -> LineageRecord:
        # 1. Load original record
        record = self._store.load(run_id)

        # 2. Pre-flight: validate all input connections can be reconstructed
        for descriptor in record.inputs:
            _reconstruct_connection(descriptor)

        # 3. Check git commit exists
        result = subprocess.run(
            ["git", "cat-file", "-e", record.git_commit],
            capture_output=True
        )
        if result.returncode != 0:
            raise MissingCommitError(
                f"Git commit '{record.git_commit}' not found in repository"
            )

        # 4. Build original_inputs mapping: name → descriptor
        original_inputs: dict[str, InputDescriptor] = {
            descriptor.name: descriptor for descriptor in record.inputs
        }

        # 5. Create git worktree for the recorded commit
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
                # 6. Import function from worktree
                sys.path.insert(0, worktree_dir)
                try:
                    module_name, func_name = record.function_ref.split(":", 1)
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                    module = importlib.import_module(module_name)
                    fn = getattr(module, func_name)
                finally:
                    sys.path.remove(worktree_dir)

                # 7. Execute via ReplayContext with original_inputs for time-travel routing
                ctx = ReplayContext(
                    run_id=replay_run_id,
                    orig_run_id=record.run_id,
                    replay_root=self._replay_root,
                    original_inputs=original_inputs,
                )
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
                        inputs=ctx.inputs,
                        outputs=ctx.outputs,
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
                    inputs=ctx.inputs,
                    outputs=ctx.outputs,
                    status="success",
                    exception_message=None,
                    original_run_id=record.run_id,
                )
                self._store.save(replay_record)
                return replay_record

            finally:
                # 8. Clean up worktree
                subprocess.run(
                    ["git", "worktree", "remove", "--force", worktree_dir],
                    capture_output=True
                )
