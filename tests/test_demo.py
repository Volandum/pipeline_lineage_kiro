"""Smoke test for demo.py (task 11.2)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_demo_runs_successfully():
    """demo.py exits 0 and prints expected output. Req 6.2, 6.3, 6.4"""
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, str(project_root / "demo.py")],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert result.returncode == 0, (
        f"demo.py exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert "Run ID:" in result.stdout
    assert "Replay Run ID:" in result.stdout
    assert "OK:" in result.stdout
