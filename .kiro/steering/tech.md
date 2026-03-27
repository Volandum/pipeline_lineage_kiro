# Tech Stack

- Language: Python (package/library)
- Packaging: `pyproject.toml` (PEP 517/518 standard)
- Package manager: `uv`
- Testing: `pytest`
- Linting/formatting: TBD (suggest `ruff` for both)

## Dependency Philosophy

- Prefer Python standard library over third-party packages
- Avoid version pinning where possible — specify only minimum versions if truly necessary
- Keep the dependency footprint minimal to maximise compatibility

## Common Commands

```bash
# Install in editable mode
uv pip install -e .

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Git Workflow

- Monorepo with feature branch deployment
- Commit frequently to feature branches
- Never rewrite history (`--force-push`, `rebase` on shared branches, and `--amend` on pushed commits are forbidden)
- Use `git revert` to undo changes on shared branches

Update this file as tooling decisions are finalized.
