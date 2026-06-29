# Status

## Current Release
**v0.7.2** (2026-06-20) — Portability release with Windows validation hardening.

## Implemented Features
- Standalone DICOM privacy auditor with recursive metadata, pixel, and sequence traversal
- Complete PS3.15 policy engine (user-local rule cache from official Part 15 DOCX)
- MIDI-B SQLite importer and 10-action evaluator
- Deterministic 10-stratum synthetic benchmark with confidence intervals and McNemar tests
- Orthanc, RSNA DICOM Anonymizer, RSNA CTP, and generic directory adapters
- Blinded human pixel/metadata review workstation with bounding boxes and Cohen's kappa
- IOD-aware context layer (user-local PS3.3-derived registry)
- Corpus-level UID, reference, pseudonym, and consistency checks
- Atomic study processing with resumable checkpoints and quarantine
- QIDO-RS, WADO-RS, and STOW-RS DICOMweb client
- Full-corpus MIDI-B live-tool campaign runner with reproducibility hashes
- Native Tk desktop interface, Streamlit web interface, and self-contained executables
- Publication-oriented CSV, JSON, LaTeX, and PNG outputs

## Validation Status
- **Unit tests**: 163 passed, 7 skipped (85.77% coverage)
- **Local release gate**: Passed (action pins, workflow integrity, dependency locks, lint, format, mypy, Bandit, compile, package builds, byte-for-byte reproducibility)
- **Synthetic end-to-end test**: Complete (demo benchmark across all 10 strata and 3 controls)
- **Public-data evaluation**: Partial (Orthanc 26.6.0 and RSNA DicomAnonymizerTool 18.0.7 run on synthetic data; MIDI-B manifest and mapping files acquired; 7 of 10 external preflight checks ready)
- **External validation**: Not completed (requires official MIDI-B DICOM corpus, answer-key database, independent reviewers, institutional authorization)

## Planned Work
- Download official MIDI-B DICOM corpus and complete full external validation
- Supply RSNA CTP pipeline execution and official validator comparison
- Execute human review with independent reviewers
- Complete native runner builds with code signing and notarization
- Begin institutional validation at governed sites
