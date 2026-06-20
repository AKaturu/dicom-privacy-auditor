# Data Dictionary

## `manifest.json`

| Field | Meaning |
|---|---|
| `benchmark_name` | Human-readable benchmark name |
| `version` | Benchmark software version |
| `manifest_version` | Ground-truth schema version |
| `seed` | Deterministic generation seed |
| `standard_reference` | DICOM standard edition used for design context |
| `cases[].case_id` | Stable synthetic case identifier |
| `cases[].relative_path` | Path to the source DICOM object |
| `cases[].clean_control` | Whether the case has no injection |
| `injections[].injection_id` | Stable injection identifier |
| `injections[].stratum` | Benchmark category |
| `injections[].location_kind` | Dataset, filename, pixel, preamble, or file-meta location |
| `injections[].path` | Expected source location |
| `injections[].value` | Artificial value; never real PHI |
| `injections[].value_sha256` | Full digest of artificial value |
| `injections[].bbox_xyxy` | Pixel rectangle when applicable |

## `run_manifest.json`

| Field | Meaning |
|---|---|
| `pipeline_name` | Workflow label |
| `pipeline_kind` | Built-in or external |
| `cases[].status` | `ok` or `error` |
| `cases[].runtime_seconds` | Wall-clock runtime |
| `cases[].output_relative_path` | Candidate output path |
| `cases[].output_sha256` | Output file digest |
| `cases[].validation` | Basic readability and consistency result |
| `cases[].pipeline_stats` | Workflow-specific counters and captured command tails |

## `evaluation.json`

| Field | Meaning |
|---|---|
| `summary.removal_rate` | Removed injections divided by all injections |
| `summary.auditor_residual_sensitivity` | Residual injections detected by configured auditor rules divided by all residual injections |
| `summary.false_positive_control_rate` | Clean controls with at least one high/critical standalone finding divided by all clean controls |
| `summary.basic_valid_outputs` | Outputs passing repository-level basic consistency checks |
| `by_stratum[]` | Performance stratified by injection category |
| `cases[].injections[].residual` | Whether the artificial identifier remains |
| `cases[].injections[].auditor_detected` | Whether the configured finding-code mapping detected the residual |
| `cases[].injections[].similarity` | Pixel-patch correlation when applicable |
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
