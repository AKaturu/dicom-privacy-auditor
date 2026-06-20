# Atomic study workflows

The study runner groups DICOM instances by `StudyInstanceUID` and processes each study as an atomic unit.

## Index studies

```bash
dicom-privacy-study index /data/source
```

## Process a local collection

```bash
dicom-privacy-study process-local \
  /data/source \
  /data/output \
  --pipeline orthanc \
  --adapter-config configs/orthanc.example.json \
  --quarantine /data/quarantine
```

Supported pipelines are `baseline`, `noop`, `orthanc`, `rsna-anonymizer`, `rsna-ctp`, and `directory`.

## Transaction behavior

- all source objects must share one non-empty Study Instance UID;
- output objects must share one candidate Study Instance UID;
- processing occurs in a staging directory on the destination filesystem;
- a complete run is atomically renamed into the publish directory;
- a partial or failed run is moved to quarantine by default;
- partial output is not silently published;
- a completed `run.json` checkpoint permits safe resume; and
- configuration SHA-256, application version, pipeline name, counts, timestamps, and failures are recorded.

`--commit-partial` exists for controlled debugging and should not be used for normal release workflows.

## Production guidance

- place source, staging, destination, and quarantine directories on encrypted storage;
- protect adapter configuration and pseudonymization secrets;
- inspect quarantine before retrying;
- run corpus consistency after every successful study batch; and
- do not copy sidecar logs or mapping files into public datasets.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
