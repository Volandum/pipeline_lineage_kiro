# Product

A Python package for lineage capture in simple data pipelines.

## Core Purpose

Track and record the lineage of data pipeline runs, capturing:
- Code used in each run
- Data sources (inputs) and sinks (outputs)
- Enough metadata to replay any past run

## Key Constraints

- Replaying a run must not overwrite existing outputs — each run's outputs are preserved
- Designed for simplicity: targets straightforward pipelines, not complex orchestration systems
