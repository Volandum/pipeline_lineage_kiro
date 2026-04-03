"""demo/pipeline.py — pipeline module for the demo notebook."""

import pandas  # noqa: F401
import file_pipeline_lineage  # noqa: F401

# Set by the notebook before Tracker.track() is called.
DB_PATH: str = ""
