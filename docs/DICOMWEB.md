# Study-level DICOMweb workflows

The DICOMweb client supports study discovery with QIDO-RS, study retrieval with WADO-RS, and instance storage with STOW-RS.

## Secure configuration

Copy `configs/dicomweb.example.json` and set authentication through environment variables rather than committing tokens or passwords.

```bash
export DICOMWEB_BEARER_TOKEN='...'
dicom-privacy-dicomweb --config source.json probe
```

Security defaults:

- HTTPS is required unless `allow_insecure_http=true`;
- `verify_tls=false` is rejected unless `allow_insecure_tls=true`;
- literal `Authorization`, `Cookie`, and `Proxy-Authorization` headers are rejected unless explicitly allowed;
- authentication values can be loaded from environment variables;
- retry counts, timeouts, request limits, and response limits are bounded; and
- HTTP error bodies are excluded by default because they may contain sensitive information.

Use `allow_insecure_http` only for a trusted local test service. Do not use insecure overrides for clinical networks.

## QIDO-RS

```bash
dicom-privacy-dicomweb --config source.json search-studies \
  --query PatientID=RESEARCH-001 \
  --query StudyDate=20250101-20251231 \
  --page-size 100 \
  --max-results 500
```

## WADO-RS

```bash
dicom-privacy-dicomweb --config source.json retrieve-study \
  1.2.840.113619.2.55.3.604688433.1234 \
  workspaces/source-study
```

The client validates that each retrieved multipart item is readable DICOM and derives a safe local filename from `SOPInstanceUID`.

## STOW-RS

```bash
dicom-privacy-dicomweb --config destination.json store-study \
  workspaces/processed-study \
  --study-uid 1.2.826.0.1.3680043.10.543.123
```

Only readable DICOM files are submitted by the CLI. The client enforces `max_request_bytes` before constructing the multipart body.

## End-to-end study workflow

```bash
dicom-privacy-study process-dicomweb \
  SOURCE_STUDY_UID \
  workspaces/dicomweb-run \
  --source-config source.json \
  --destination-config destination.json \
  --pipeline orthanc \
  --adapter-config configs/orthanc.example.json
```

The workflow retrieves the source study, processes all instances in one staging directory, and uploads only when the entire study finishes successfully. Partial or failed runs are quarantined and are not submitted through STOW-RS.

## Current scaling boundary

WADO-RS and STOW-RS multipart bodies are bounded but currently assembled in memory. Configure conservative request/response limits and process one study at a time. Streaming multipart processing is a future optimization for exceptionally large studies.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
