"""Demo pipeline module.

Defines the pipeline function and custom connections used by the demo notebook.
The module-level DB_PATH variable is set by the notebook before Tracker.track() is called.
"""

import pandas as pd  # noqa: F401

import file_pipeline_lineage  # noqa: F401

# Set by the notebook setup cell before running the pipeline.
DB_PATH: str = ""
