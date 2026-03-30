"""RunContext and ReplayContext for I/O interception and lineage capture."""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from file_pipeline_lineage.connections import Connection, OverwriteStatus, WriteResult
from file_pipeline_lineage.descriptors import InputDescriptor, OutputDescriptor
from file_pipeline_lineage.exceptions import DuplicateNameError

if TYPE_CHECKING:
    pass


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _connection_class_path(connection: Connection) -> str:
    """Return the fully-qualified import path for a connection's class."""
    t = type(connection)
    return f"{t.__module__}:{t.__qualname__}"


def _auto_name(index: int, connection: Connection) -> str:
    """Generate an auto-name: ``<index>:<ClassName>(<truncated_params>)``.

    The params portion is a comma-separated ``key=value`` representation of
    ``connection.serialise()``, truncated to at most 50 characters with a
    trailing ``...`` if truncated.  The full name (including index and class
    name) may therefore exceed 50 characters — only the *params* portion is
    capped.
    """
    class_name = type(connection).__name__
    params_dict = connection.serialise()
    params_str = ", ".join(f"{k}={v}" for k, v in params_dict.items())
    if len(params_str) > 50:
        params_str = params_str[:50] + "..."
    return f"{index}:{class_name}({params_str})"


class RunContext:
    """I/O interception object passed to every pipeline function.

    Records all input and output connections accessed during a run.
    Accepts only ``Connection`` objects — plain path strings are no longer
    supported (breaking change from the original implementation).
    """

    def __init__(self, run_id: str, base_output_dir: str | Path | None = None) -> None:
        self._run_id = run_id
        self._base_output_dir = Path(base_output_dir) if base_output_dir is not None else Path(".")
        self._inputs: list[InputDescriptor] = []
        self._outputs: list[OutputDescriptor] = []
        # Track names for duplicate detection
        self._input_names: set[str] = set()
        self._output_names: set[str] = set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_input_name(self, connection: Connection, name: str | None) -> str:
        if name is None:
            name = _auto_name(len(self._inputs) + 1, connection)
        if name in self._input_names:
            raise DuplicateNameError(
                f"Input name {name!r} is already in use within this run."
            )
        return name

    def _resolve_output_name(self, connection: Connection, name: str | None) -> str:
        if name is None:
            name = _auto_name(len(self._outputs) + 1, connection)
        if name in self._output_names:
            raise DuplicateNameError(
                f"Output name {name!r} is already in use within this run."
            )
        return name

    # ------------------------------------------------------------------
    # Public I/O methods
    # ------------------------------------------------------------------

    def open_input(self, connection: Connection, name: str | None = None):
        """Record an input and return the result of ``connection.read(None)``."""
        resolved_name = self._resolve_input_name(connection, name)
        access_timestamp = _utc_now_iso()
        result = connection.read(None)
        descriptor = InputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            access_timestamp=access_timestamp,
            time_travel=False,
        )
        self._inputs.append(descriptor)
        self._input_names.add(resolved_name)
        return result

    def atomic_read(self, connection: Connection, name: str | None = None):
        """Record an input and return the result of ``connection.atomic_read(None)``."""
        resolved_name = self._resolve_input_name(connection, name)
        access_timestamp = _utc_now_iso()
        result = connection.atomic_read(None)
        descriptor = InputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            access_timestamp=access_timestamp,
            time_travel=False,
        )
        self._inputs.append(descriptor)
        self._input_names.add(resolved_name)
        return result

    def open_output(self, connection: Connection, name: str | None = None, overwrite: bool = False):
        """Record an output and return the context manager from ``connection.write()``.

        If the connection is a ``LocalConnection`` with ``base_output_dir=None``,
        the context's ``_base_output_dir`` is injected before calling ``write()``.

        The descriptor is appended immediately with ``overwrite_status="in_progress"``.
        When the context manager's ``__exit__`` fires successfully, the descriptor is
        updated to the final ``WriteResult`` status.
        """
        # Inject base_output_dir for LocalConnection when not set
        from file_pipeline_lineage.connections import LocalConnection  # noqa: PLC0415
        if isinstance(connection, LocalConnection) and connection.base_output_dir is None:
            connection = LocalConnection(connection.path, base_output_dir=self._base_output_dir)

        resolved_name = self._resolve_output_name(connection, name)
        descriptor = OutputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            overwrite_requested=overwrite,
            overwrite_status=OverwriteStatus.IN_PROGRESS.value,
        )
        self._outputs.append(descriptor)
        self._output_names.add(resolved_name)
        # Index of this descriptor so we can update it later
        descriptor_index = len(self._outputs) - 1

        ctx_mgr = connection.write(run_id=self._run_id, overwrite=overwrite)

        @contextlib.contextmanager
        def _wrapping_ctx():
            with ctx_mgr as resource:
                yield resource
            # __exit__ succeeded — update descriptor to final status
            write_result: WriteResult | None = getattr(ctx_mgr, "result", None)
            if write_result is not None:
                final_status = write_result.overwrite_status.value
            else:
                final_status = OverwriteStatus.UNKNOWN.value
            self._outputs[descriptor_index] = OutputDescriptor(
                name=resolved_name,
                connection_class=_connection_class_path(connection),
                connection_args=connection.serialise(),
                overwrite_requested=overwrite,
                overwrite_status=final_status,
            )

        return _wrapping_ctx()

    def atomic_write(self, connection: Connection, data, name: str | None = None, overwrite: bool = False):
        """Record an output and call ``connection.atomic_write(data, run_id, overwrite)``."""
        resolved_name = self._resolve_output_name(connection, name)
        write_result: WriteResult | None = connection.atomic_write(
            data, run_id=self._run_id, overwrite=overwrite
        )
        if write_result is not None:
            final_status = write_result.overwrite_status.value
        else:
            final_status = OverwriteStatus.UNKNOWN.value
        descriptor = OutputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            overwrite_requested=overwrite,
            overwrite_status=final_status,
        )
        self._outputs.append(descriptor)
        self._output_names.add(resolved_name)
        return write_result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def inputs(self) -> tuple[InputDescriptor, ...]:
        return tuple(self._inputs)

    @property
    def outputs(self) -> tuple[OutputDescriptor, ...]:
        return tuple(self._outputs)


class ReplayContext(RunContext):
    """RunContext subclass used by the Replayer.

    Overrides ``open_input`` and ``atomic_read`` to apply time-travel routing:
    if the connection supports time travel, the recorded ``access_timestamp``
    is passed; otherwise a live read (``None``) is performed.

    ``open_output`` and ``atomic_write`` are inherited unchanged — replay does
    not re-write outputs.
    """

    def __init__(
        self,
        run_id: str,
        orig_run_id: str,
        replay_root: str | Path,
        original_inputs: dict[str, InputDescriptor] | None = None,
    ) -> None:
        # Output path structure: replay_root / orig_run_id / replay_run_id / filename
        super().__init__(run_id, Path(replay_root) / orig_run_id)
        self._orig_run_id = orig_run_id
        self._replay_root = Path(replay_root)
        self._original_inputs: dict[str, InputDescriptor] = original_inputs or {}

    def open_input(self, connection: Connection, name: str | None = None):
        """Time-travel-aware open_input.

        Looks up the original descriptor by name, then routes to
        ``connection.read(access_timestamp)`` or ``connection.read(None)``
        depending on ``connection.supports_time_travel``.
        """
        resolved_name = self._resolve_input_name(connection, name)
        descriptor = self._original_inputs.get(resolved_name)
        access_timestamp = _utc_now_iso()
        time_travel = False

        if descriptor is not None and connection.supports_time_travel:
            result = connection.read(descriptor.access_timestamp)
            access_timestamp = descriptor.access_timestamp
            time_travel = True
        else:
            result = connection.read(None)

        recorded = InputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            access_timestamp=access_timestamp,
            time_travel=time_travel,
        )
        self._inputs.append(recorded)
        self._input_names.add(resolved_name)
        return result

    def atomic_read(self, connection: Connection, name: str | None = None):
        """Time-travel-aware atomic_read."""
        resolved_name = self._resolve_input_name(connection, name)
        descriptor = self._original_inputs.get(resolved_name)
        access_timestamp = _utc_now_iso()
        time_travel = False

        if descriptor is not None and connection.supports_time_travel:
            result = connection.atomic_read(descriptor.access_timestamp)
            access_timestamp = descriptor.access_timestamp
            time_travel = True
        else:
            result = connection.atomic_read(None)

        recorded = InputDescriptor(
            name=resolved_name,
            connection_class=_connection_class_path(connection),
            connection_args=connection.serialise(),
            access_timestamp=access_timestamp,
            time_travel=time_travel,
        )
        self._inputs.append(recorded)
        self._input_names.add(resolved_name)
        return result
