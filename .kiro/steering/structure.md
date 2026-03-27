# Project Structure

Standard Python package layout:

```
src/
  <package_name>/     # Main package source
    __init__.py
tests/                # pytest test suite
pyproject.toml        # Package metadata and build config
README.md
.kiro/                # Kiro AI assistant configuration
  steering/           # AI steering documents
```

## Conventions

- Source lives under `src/` (src layout) to avoid import confusion
- Tests mirror the package structure where practical
- Public API is explicitly defined in `__init__.py`
- Keep lineage capture logic decoupled from pipeline execution logic
