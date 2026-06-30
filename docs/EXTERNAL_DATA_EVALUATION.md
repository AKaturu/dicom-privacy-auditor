# External Data Evaluation

This repository may be evaluated with external public or institutionally governed data stored outside the Git checkout.

Set the external data root with an environment variable:

```bash
export EXTERNAL_DATA_ROOT=/path/to/RadiologyExternalValidation
```

On Windows PowerShell:

```powershell
$env:EXTERNAL_DATA_ROOT = "<external-data-root>"
```

Do not commit raw datasets, downloaded terminology files, credentials, model weights, large predictions, caches, or local machine paths. Public reports should use placeholders such as `${EXTERNAL_DATA_ROOT}` and should distinguish software tests, synthetic benchmarks, public-data evaluations, and clinical validation.

Current evidence status for this project is tracked in the external validation workspace, not in this repository.

For MIDI-B runs, configure the answer-key database plus both official mapping CSVs:

- `midi_b_uid_mapping`
- `midi_b_patient_mapping`

These files are fingerprinted by `dicom-privacy-external` when fingerprinting is enabled. They
should stay outside Git with the answer-key database.

The external preflight can also monitor an official validator run when the local config includes
`official_validator_output_dir`, `official_validator_log_dir`, and `official_validator_run_name`.
The monitor only reports status, artifact presence, DB size, and log error counts; it does not
publish raw answer-key rows, DICOM objects, or unredacted local paths.
