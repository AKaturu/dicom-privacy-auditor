# Blockers

Final status is `PARTIALLY COMPLETE — EXTERNAL BLOCKERS REMAIN`.

## Required External Resources Not Supplied

- Official MIDI-B validation DICOM collection.
- Frozen MIDI-B test DICOM collection.
- MIDI-B SQLite answer key.
- Patient mapping file.
- UID mapping file.
- Official MIDI-B validator executable/script and documented invocation.
- Orthanc pinned version or immutable container digest plus dedicated instance configuration.
- RSNA DICOM Anonymizer executable/version/hash and project model.
- RSNA CTP installation/JAR/version/hash and pipeline configuration.
- Additional independent open-source or institutionally approved workflow.
- Two trained independent blinded human reviewers.
- One qualified adjudicator.
- Authorized institutional PACS/DICOMweb endpoint and written authorization, if that optional phase is desired.
- Windows/macOS GitHub Actions run IDs, runner images, logs, and artifacts.
- Owner-controlled Authenticode credentials.
- Owner-controlled Apple Developer ID/notary credentials.

## Attempted Resolution

- Verified all user-supplied handoff and release artifacts.
- Read the protocol and execution documents.
- Ran and repaired the local release gate for the local Windows/Python environment.
- Prepared `validation/codex/external-validation.json` and external preflight commands.
- Confirmed missing-resource behavior must be recorded rather than simulated.

## Required User Action

Provide the missing resources through secure local paths, environment variables, mounted approved storage, authorized repositories, protected reviewer workstations, or approved secret stores. Do not paste secrets, PHI, reviewer identity mappings, signing keys, or institutional endpoint tokens into chat or source files.
