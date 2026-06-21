# Synthetic demonstration

The GitHub-facing demo path is intentionally synthetic-only. Use it for screenshots, videos, CI smoke checks, tutorials, and public examples. Do not use TCIA/Synapse/institutional DICOM objects for the default demo workspace.

Run:

```bash
dicom-privacy-demo demo-release --cases-per-stratum 1 --clean-controls 2 --overwrite
```

The output contains:

- `benchmark/`: synthetic source objects and injection manifest
- `run-*`: no-op, metadata-only, and benchmark-aware baseline outputs
- `evaluation-*`: JSON, CSV, Markdown, and optional figures
- `corpus-report.json`: collection-level consistency analysis
- `human-review.db`: pending source/candidate review cases
- `publication/`: manuscript-ready tables and templates
- `demo_manifest.json`: validated run manifest

The baseline is a positive control informed by benchmark bounding boxes. It must not be presented as a production de-identification method. All cases and identifiers are synthetic.

Real MIDI-B or institutional data can be used for governed validation, but keep it outside the repository and follow [Real data setup](REAL_DATA_SETUP.md).
