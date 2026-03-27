"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class PipelineRepo:
    repo_path: Path
    commit_sha: str
    function_ref: str
    input_file: Path


@pytest.fixture(scope="session")
def pipeline_git_repo(tmp_path_factory):
    """Create a temp git repo with a committed simple_pipeline function.

    simple_pipeline writes deterministic content to output.txt — no inputs required.
    An input.txt file is also created for tests that need a real input_paths entry.
    """
    repo = tmp_path_factory.mktemp("pipeline_repo")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo, check=True, capture_output=True,
    )

    # Write the pipeline module — deterministic output, no inputs needed
    pipeline_src = (
        'def simple_pipeline(ctx):\n'
        '    with ctx.open_output("output.txt", "w") as f:\n'
        '        f.write("hello from simple_pipeline")\n'
    )
    (repo / "pipelines.py").write_text(pipeline_src)
    subprocess.run(["git", "add", "pipelines.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add pipeline"],
        cwd=repo, check=True, capture_output=True,
    )

    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    # Create a real input file for tests that need non-empty input_paths
    input_file = repo / "input.txt"
    input_file.write_bytes(b"hello replay")

    return PipelineRepo(
        repo_path=repo,
        commit_sha=commit_sha,
        function_ref="pipelines:simple_pipeline",
        input_file=input_file,
    )
