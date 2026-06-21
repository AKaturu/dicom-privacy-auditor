# Live validation records

This directory is intentionally empty in source releases. Add one subdirectory per externally executed validation campaign.

The public GitHub project should use synthetic data for demos and examples. Real validation records belong here only after the corpus, answer key, reviewer process, and tool versions have been governed and redacted. Never commit source DICOM data or answer-key databases.

Recommended contents:

```text
validation/live/YYYY-MM-DD-tool-version/
├── STATUS.md
├── environment.json
├── tool-config.redacted.json
├── tool-config.sha256
├── campaign.json
├── internal-evaluation/
├── official-evaluation/
├── corpus-report.json
├── review-export.json
└── SHA256SUMS.txt
```

A live validation record should state the MIDI-B collection/version, exact tool version, configuration digest, operating system, hardware, start/end timestamps, processing failures, internal score, official score, parity findings, reviewer procedures, and known deviations.

Do not commit source DICOM data, reversible mappings, credentials, raw PHI, or unredacted local paths.
