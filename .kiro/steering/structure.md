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

## Document Formatting

All project documents (specs, design docs, README, INTERFACES.md, steering files) must follow these conventions:

- Every document must have a table of contents with anchor links to each section
- Each section must be no more than 30 lines
- If a section would exceed 30 lines, split it into named sub-sections, each with their own anchor link
