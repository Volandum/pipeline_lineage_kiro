# Project Structure

Standard Python package layout:

```
src/
  <package_name>/     # Main package source
    __init__.py
tests/                # pytest test suite
pyproject.toml        # Package metadata and build config
README.md
INTERFACES.md         # Interface documentation: data models and public APIs
.kiro/                # Kiro AI assistant configuration
  steering/           # AI steering documents
```

## Conventions

- Source lives under `src/` (src layout) to avoid import confusion
- Tests mirror the package structure where practical
- Public API is explicitly defined in `__init__.py`
- Keep lineage capture logic decoupled from pipeline execution logic
- Interface documentation (data models and public APIs) must be maintained in `INTERFACES.md` at the project root — keep it up to date as the public API evolves
