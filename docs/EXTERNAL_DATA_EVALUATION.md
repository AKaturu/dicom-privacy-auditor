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
