"""RunContext and ReplayContext for I/O interception and lineage capture."""

from __future__ import annotations

from pathlib import Path
from typing import IO


class RunContext:
    """I/O interception object passed to every pipeline function.

    Records all input and output paths accessed during a run.
    Output files are written to <base_output_dir>/<run_id>/<filename>.
    """

    def __init__(self, run_id: str, base_output_dir: str | Path) -> None:
        self._run_id = run_id
        self._base_output_dir = Path(base_output_dir)
        self._inputs: list[str] = []
        self._outputs: list[str] = []

    def open_input(self, path: str | Path, mode: str = "r", **kwargs) -> IO:
        """Record path in inputs and delegate to open()."""
        self._inputs.append(str(path))
        return open(path, mode, **kwargs)

    def open_output(self, path: str | Path, mode: str = "w", **kwargs) -> IO:
        """Resolve to <base_output_dir>/<run_id>/<filename>, create dirs, record, open."""
        resolved = self._base_output_dir / self._run_id / Path(path).name
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._outputs.append(str(resolved))
        return open(resolved, mode, **kwargs)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def inputs(self) -> tuple[str, ...]:
        return tuple(self._inputs)

    @property
    def outputs(self) -> tuple[str, ...]:
        return tuple(self._outputs)


class ReplayContext(RunContext):
    """RunContext subclass used by the Replayer.

    Overrides open_output() to write to
    <replay_root>/<orig_run_id>/<run_id>/<filename> instead of the
    base_output_dir path, ensuring replay outputs are fully isolated.
    """

    def __init__(
        self,
        run_id: str,
        orig_run_id: str,
        replay_root: str | Path,
    ) -> None:
        # base_output_dir is unused in ReplayContext but required by parent
        super().__init__(run_id, replay_root)
        self._orig_run_id = orig_run_id
        self._replay_root = Path(replay_root)

    def open_output(self, path: str | Path, mode: str = "w", **kwargs) -> IO:
        """Resolve to <replay_root>/<orig_run_id>/<run_id>/<filename>."""
        resolved = self._replay_root / self._orig_run_id / self._run_id / Path(path).name
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._outputs.append(str(resolved))
        return open(resolved, mode, **kwargs)
