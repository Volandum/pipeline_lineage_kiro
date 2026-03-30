"""Unit tests for WriteResult and OverwriteStatus."""

import pytest

from file_pipeline_lineage.connections import OverwriteStatus, WriteResult


class TestOverwriteStatus:
    def test_overwrite_serialises_to_lowercase(self):
        assert OverwriteStatus.OVERWRITE.value == "overwrite"

    def test_no_overwrite_serialises_to_lowercase(self):
        assert OverwriteStatus.NO_OVERWRITE.value == "no_overwrite"

    def test_unknown_serialises_to_lowercase(self):
        assert OverwriteStatus.UNKNOWN.value == "unknown"

    def test_in_progress_serialises_to_lowercase(self):
        assert OverwriteStatus.IN_PROGRESS.value == "in_progress"

    def test_is_str_subclass(self):
        # OverwriteStatus(str, Enum) — values are strings
        assert isinstance(OverwriteStatus.OVERWRITE, str)
        assert OverwriteStatus.OVERWRITE == "overwrite"


class TestWriteResult:
    def test_frozen_raises_on_attribute_assignment(self):
        result = WriteResult(overwrite_status=OverwriteStatus.NO_OVERWRITE)
        with pytest.raises((AttributeError, TypeError)):
            result.overwrite_status = OverwriteStatus.OVERWRITE  # type: ignore[misc]

    def test_stores_overwrite_status(self):
        result = WriteResult(overwrite_status=OverwriteStatus.OVERWRITE)
        assert result.overwrite_status == OverwriteStatus.OVERWRITE

    def test_equality(self):
        a = WriteResult(OverwriteStatus.NO_OVERWRITE)
        b = WriteResult(OverwriteStatus.NO_OVERWRITE)
        assert a == b

    def test_inequality(self):
        a = WriteResult(OverwriteStatus.OVERWRITE)
        b = WriteResult(OverwriteStatus.NO_OVERWRITE)
        assert a != b
