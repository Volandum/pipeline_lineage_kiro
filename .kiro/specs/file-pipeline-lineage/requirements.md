# Requirements Document

## Introduction

A Python package MVP that captures lineage for file-based data pipeline runs. The package records the code, input files, output files, and metadata for each run, and provides a replay capability that re-executes any past run while preserving all prior outputs by writing replay results to isolated, timestamped locations.

## Glossary

- **Pipeline**: A user-defined transformation that reads one or more input files and writes one or more output files.
- **Run**: A single execution of a Pipeline, identified by a unique run ID and timestamp.
- **Lineage_Record**: The persisted metadata for a Run, including the git commit SHA, function reference, input file references, output file references, and execution metadata.
- **Lineage_Store**: The component responsible for persisting and retrieving Lineage_Records.
- **Tracker**: The component that wraps Pipeline execution, captures lineage, and writes Lineage_Records to the Lineage_Store.
- **Replayer**: The component that reads a Lineage_Record and re-executes the captured Pipeline code against the original inputs, writing outputs to a new isolated location.
- **Input_File**: A file path (or set of file paths) consumed as input by a Pipeline.
- **Output_File**: A file path (or set of file paths) produced as output by a Pipeline.
- **Replay_Run**: A Run produced by the Replayer re-executing a prior Run's code and inputs.
- **Run_ID**: A unique identifier (UUID) assigned to each Run and Replay_Run.
- **Git_Commit**: The full SHA of the HEAD git commit recorded at the time a Run is initiated, used to identify the exact version of code that executed.
- **Function_Ref**: A fully-qualified reference to a pipeline function in the form `module.submodule:function_name`, used to locate and import the function during replay.
- **RunContext**: An object provided by the Tracker to the pipeline function that intercepts all file I/O. The pipeline calls `ctx.open_input(path)` and `ctx.open_output(path)` instead of plain `open()`. The `RunContext` records the actual paths accessed and delegates to the real filesystem.
- **ReplayContext**: A specialisation of `RunContext` used by the Replayer. It passes input paths through unchanged and rewrites output paths to the isolated replay directory (`<replay_root>/<orig_run_id>/<replay_run_id>/<filename>`).
- **base_output_dir**: The base directory provided to `Tracker.track()`. The `RunContext` constructs actual output paths as `<base_output_dir>/<run_id>/<filename>`, guaranteeing per-run output isolation.

---

## Requirements

### Requirement 1: Lineage Capture for File-Based Pipelines

**User Story:** As a data engineer, I want the Tracker to record lineage for every pipeline run, so that I have a complete audit trail of what code ran, what files were consumed, and what files were produced.

#### Acceptance Criteria

1. WHEN a Pipeline run completes successfully, THE Tracker SHALL record a Lineage_Record containing: the Run_ID, UTC timestamp, the git commit SHA, the fully-qualified function reference, the list of Input_File paths, and the list of Output_File paths.
2. THE Tracker SHALL assign a unique Run_ID (UUID4) to each Run before execution begins.
3. WHEN a Pipeline accepts multiple Input_Files, THE Tracker SHALL record all Input_File paths in the Lineage_Record.
4. WHEN a Pipeline produces multiple Output_Files, THE Tracker SHALL record all Output_File paths in the Lineage_Record.
5. IF a Pipeline run raises an exception, THEN THE Tracker SHALL record a Lineage_Record with a failed status, the exception message, and all Output_File paths that were opened for writing via `ctx.open_output()` before the exception was raised (as captured in `ctx.outputs` at the time of the exception), and SHALL re-raise the original exception.
6. THE Tracker SHALL provide a `RunContext` to the pipeline function; the pipeline function SHALL use `ctx.open_input(path)` and `ctx.open_output(path)` for all file I/O, and the Tracker SHALL record inputs and outputs from the actual I/O calls intercepted by the `RunContext` rather than from upfront declarations.

---

### Requirement 2: Lineage Storage

**User Story:** As a data engineer, I want lineage records persisted to disk, so that they survive process restarts and can be queried later.

#### Acceptance Criteria

1. THE Lineage_Store SHALL persist each Lineage_Record as a JSON file on the local filesystem.
2. THE Lineage_Store SHALL store each Lineage_Record under a path derived from the Run_ID so that records do not collide.
3. WHEN a Lineage_Record is written, THE Lineage_Store SHALL ensure the record is fully written before returning.
4. WHEN a Run_ID is provided, THE Lineage_Store SHALL retrieve the corresponding Lineage_Record.
5. IF a requested Run_ID does not exist in the store, THEN THE Lineage_Store SHALL raise a descriptive error identifying the missing Run_ID.
6. THE Lineage_Store SHALL support listing all stored Run_IDs.

---

### Requirement 3: Run Replay

**User Story:** As a data engineer, I want to replay any past pipeline run, so that I can reproduce results or debug issues without manually reconstructing the original execution.

#### Acceptance Criteria

1. WHEN a Run_ID is provided to the Replayer, THE Replayer SHALL load the corresponding Lineage_Record from the Lineage_Store.
2. WHEN replaying a Run, THE Replayer SHALL execute the pipeline function captured in the Lineage_Record against the original Input_File paths.
3. WHEN replaying a Run, THE Replayer SHALL provide a `ReplayContext` to the pipeline function that rewrites all `ctx.open_output()` calls to the isolated replay directory `<replay_root>/<original_run_id>/<replay_run_id>/<original_filename>`, so that replay outputs are distinguishable from original outputs and from other replays of the same run.
4. WHEN a replay completes, THE Replayer SHALL record a new Lineage_Record for the Replay_Run, referencing the original Run_ID as its source.
5. IF the original Input_Files referenced in a Lineage_Record no longer exist at their recorded paths, THEN THE Replayer SHALL raise a descriptive error identifying the missing files before attempting execution.

---

### Requirement 4: Output Preservation (No Overwrite)

**User Story:** As a data engineer, I want each run's outputs to be preserved independently, so that replaying a run never destroys or overwrites the results of any prior run.

#### Acceptance Criteria

1. WHEN a Replay_Run produces Output_Files, THE Replayer SHALL write those files to a path that is distinct from the original Run's Output_File paths.
2. WHEN multiple Replay_Runs are performed for the same original Run_ID, THE Replayer SHALL write each Replay_Run's outputs to a separate directory, differentiated by the Replay_Run's own Run_ID.
3. THE Replayer SHALL NOT modify or delete any Output_File produced by a prior Run or Replay_Run.

---

### Requirement 5: Code Snapshot

**User Story:** As a data engineer, I want the exact version of the pipeline function to be captured at run time via its git commit and importable reference, so that I can re-execute the precise logic that produced a given output.

#### Acceptance Criteria

1. WHEN a Pipeline run is initiated, THE Tracker SHALL record the current git commit SHA (the output of `git rev-parse HEAD`) in the Lineage_Record.
2. THE Tracker SHALL record the fully-qualified function reference (e.g. `mypackage.pipelines:transform`) in the Lineage_Record.
3. THE Lineage_Record SHALL store the git commit SHA and function reference as plain strings.
4. WHEN replaying a Run, THE Replayer SHALL check out the recorded git commit into a temporary working tree and import the function by its recorded reference to execute it.
5. IF the recorded git commit does not exist in the repository, THE Replayer SHALL raise a descriptive error before attempting execution.

---

### Requirement 6: Replay Demonstration

**User Story:** As a developer evaluating this package, I want a runnable example script that demonstrates lineage capture and replay end-to-end, so that I can understand the package's capabilities quickly.

#### Acceptance Criteria

1. THE package SHALL include a demonstration script that defines a file-based pipeline with at least one Input_File and at least one Output_File.
2. WHEN the demonstration script is executed, THE script SHALL perform an initial pipeline run and print the resulting Run_ID.
3. WHEN the demonstration script is executed, THE script SHALL replay the initial run using the Replayer and print the Replay_Run's Run_ID and output location.
4. WHEN the demonstration script is executed, THE script SHALL verify that the original Output_Files and the Replay_Run Output_Files exist at their respective distinct paths and print a confirmation.

---

### Requirement 7: Concurrent Run Safety

**User Story:** As a data engineer, I want multiple pipeline runs executing simultaneously to remain fully isolated from one another, so that concurrent execution never causes lineage records or output files to collide or corrupt each other.

#### Acceptance Criteria

1. THE Tracker SHALL assign each Run a Run_ID (UUID4) before execution begins, such that two concurrently starting Runs are guaranteed to receive distinct Run_IDs.
2. WHEN multiple Runs execute concurrently, THE Lineage_Store SHALL write each Lineage_Record to a path derived solely from its Run_ID, so that no two concurrent writes target the same file path.
3. WHEN multiple Runs execute concurrently, THE Lineage_Store SHALL write each Lineage_Record atomically (write to a temporary file then rename), so that a partial write from one Run is never visible to a reader as a complete record.
4. WHEN multiple Runs execute concurrently, THE Tracker SHALL ensure each Run's Output_Files are written to `<base_output_dir>/<run_id>/<filename>` (constructed by the `RunContext`), so that concurrent runs cannot write to the same output path by construction.
