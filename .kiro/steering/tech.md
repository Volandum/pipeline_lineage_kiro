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

## Shell

Default terminal is PowerShell. Use `;` as the command separator (not `&&`). Avoid bash-specific syntax.

## Common Commands

```powershell
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
- Whenever steering documents or `INTERFACES.md` are updated, commit those changes immediately and atomically with any related code changes
- After completing each implementation task (or sub-task), commit all changes with a message referencing the task number, e.g. `feat: task 3.1 — implement LineageStore save/load`
- When committing a completed task, always include the `tasks.md` update (marking the task `[x]`) in the same commit as the implementation changes

Update this file as tooling decisions are finalized.
