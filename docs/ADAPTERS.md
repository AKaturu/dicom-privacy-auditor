# External de-identification adapters

Adapters process one DICOM object at a time and write the resulting candidate object into the benchmark run directory. They do not imply endorsement, certification, or equivalent configuration across tools.

## Common commands

```bash
dicom-privacy-adapter probe orthanc configs/orthanc.json

dicom-privacy-adapter process orthanc configs/orthanc.json \
  source.dcm candidate.dcm --case-id case-001

dicom-privacy-adapter run-benchmark orthanc configs/orthanc.json \
  benchmark/ run-orthanc/ --overwrite
```

The same commands accept `rsna-anonymizer`, `rsna-ctp`, or `directory`.

## Orthanc

The Orthanc adapter:

1. uploads the source object with `POST /instances`;
2. requests single-instance anonymization with `POST /instances/{id}/anonymize`;
3. saves the returned DICOM bytes;
4. deletes the temporary uploaded source only when the upload was newly stored.

An Orthanc response of `AlreadyStored` is **not deleted by default**, because it may refer to an object that existed before the benchmark run.

Example:

```json
{
  "base_url": "https://orthanc.example.org",
  "username_env": "DPA_ORTHANC_USERNAME",
  "password_env": "DPA_ORTHANC_PASSWORD",
  "verify_tls": true,
  "allow_insecure_http": false,
  "allow_insecure_tls": false,
  "allow_literal_credentials": false,
  "include_error_body": false,
  "dicom_version": "2023b",
  "keep_private_tags": false,
  "cleanup_uploaded": true,
  "cleanup_already_stored": false,
  "timeout_seconds": 120,
  "max_request_bytes": 2147483648,
  "max_response_bytes": 2147483648
}
```

Orthanc currently documents `2008`, `2017c`, `2021b`, and `2023b` for its `DicomVersion` parameter. This is independent of the auditor's user-generated PS3.15 rule cache and must be reported in comparative studies.

Use a dedicated Orthanc instance for benchmarking. Do not point automated cleanup at a clinical archive. Remote HTTP endpoints are rejected by default, TLS verification is enabled by default, and credentials should be supplied through environment variables. Literal credentials require an explicit unsafe compatibility flag.

## RSNA DICOM Anonymizer

The adapter can connect to an already-running RSNA Anonymizer DICOM SCP or launch headless mode using the current command form:

```bash
rsna-anonymizer -c /path/to/ProjectModel.json
```

It sends one instance by C-STORE and collects the newly written output from a dedicated storage tree. Install the adapter dependency:

```bash
pip install -e ".[adapters]"
```

Key configuration fields:

```json
{
  "host": "127.0.0.1",
  "port": 1045,
  "called_ae_title": "ANONYMIZER",
  "calling_ae_title": "DPAUDITOR",
  "output_dir": "/dedicated/project/storage",
  "project_model": "/path/to/ProjectModel.json",
  "startup_seconds": 5,
  "timeout_seconds": 120,
  "poll_seconds": 0.5,
  "max_input_bytes": 2147483648,
  "max_output_bytes": 2147483648,
  "cleanup_output": true
}
```

The output tree must be dedicated to the benchmark. Concurrent external writes can make file attribution ambiguous. Input and output byte limits default to 2 GiB. The collected output is copied atomically with owner-only permissions and the transient file in the watched tree is deleted by default; set `cleanup_output` to `false` only when governed retention is required.

## RSNA CTP

CTP is integrated through a dedicated watched-directory pipeline. Configure CTP with a directory or archive import stage, the DICOM anonymizer processor, and a directory/file storage stage. The adapter places one object into the configured input directory and waits for a stable newly created output object.

```json
{
  "input_dir": "/path/to/ctp/pipeline/incoming",
  "output_dir": "/path/to/ctp/pipeline/outgoing",
  "start_command": ["java", "-jar", "/path/to/CTP/Runner.jar"],
  "working_directory": "/path/to/CTP",
  "startup_seconds": 5,
  "timeout_seconds": 120,
  "poll_seconds": 0.5,
  "max_input_bytes": 2147483648,
  "max_output_bytes": 2147483648,
  "cleanup_output": true,
  "stop_process_on_close": true
}
```

Because CTP installations and launch scripts vary, `start_command` is explicit rather than guessed. The adapter also works with an already-running CTP process by omitting `start_command`. Input and output roots must be separate, non-symbolic-link directories. Transfers default to 2 GiB limits, destination copies are owner-only and atomic, and transient pipeline output is removed by default after collection.

## Reproducible comparison checklist

Record for every run:

- tool name and exact version;
- configuration/project/anonymizer-script checksum;
- adapter configuration with credentials removed;
- source benchmark version and answer-key checksum;
- whether filenames were preserved or safely replaced;
- runtime environment and transfer syntaxes;
- errors, quarantines, and unreadable outputs;
- any manual review or post-processing.

## Validation status

- Orthanc REST behavior is tested with a mocked HTTP service, including the `AlreadyStored` safety condition.
- RSNA CTP directory behavior is tested with a simulated asynchronous pipeline.
- RSNA Anonymizer C-ECHO and C-STORE behavior is tested end to end against a local `pynetdicom` SCP that writes an anonymized output; a live RSNA project was not available in the local build environment.

Run a small local smoke study against each real installation before attempting the full benchmark.

## Optional live Orthanc smoke test

A pinned local Orthanc container is provided for integration testing:

```bash
docker compose -f compose.orthanc.yml up -d
python scripts/smoke_orthanc.py
docker compose -f compose.orthanc.yml down -v
```

Run this only against the dedicated container. The final local-completion environment did not provide a Docker or Podman daemon, so this live container smoke test remains supplied for execution on a host with an available container runtime.
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
