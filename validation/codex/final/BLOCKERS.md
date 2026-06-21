# Blockers

Final status is `PARTIALLY COMPLETE - EXTERNAL BLOCKERS REMAIN`.

Post-release real-source evidence improved the external preflight to 7 of 10 required checks ready. Public CBIIT validator source, Python 3.12 RSNA anonymizer tooling, IBM Aspera transfer tooling, public TCIA manifests/mappings, Orthanc, DICOMweb, DIMSE, and credential-presence checks are all represented in the loose evidence files. Packaged v0.7.2 release artifacts were not rebuilt by this addendum.

## Required External Resources Not Supplied

- Official MIDI-B validation DICOM collection. Public `.tcia` manifests were acquired, but the DICOM corpus has not been downloaded.
- Frozen MIDI-B test DICOM collection.
- MIDI-B SQLite answer key. Public TCIA/Faspex package IDs were identified, but the answer-key database still requires an authenticated Faspex bearer-token transfer.
- Patient mapping file. Public mapping CSVs were acquired; official answer-key validation still needs the answer DB and corpus.
- UID mapping file. Public mapping CSVs were acquired; official answer-key validation still needs the answer DB and corpus.
- RSNA CTP working pipeline configuration. The installation is acquired and command-discoverable, but `Runner.jar -help` throws `NullPointerException` and no CTP pipeline execution is claimed.
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
- Prepared external preflight configs and command wrappers.
- Downloaded public TCIA MIDI-B manifests and mapping CSVs to `D:/CodexExternal/MIDI-B` and recorded hashes in `validation/codex/external/MIDI_B_PUBLIC_RESOURCE_INVENTORY.json`.
- Installed Python 3.12.10 and `rsna-anonymizer` 18.0.7; `rsna-anonymizer --help` passed.
- Cloned CBIIT `MIDI_validation_script`, installed its Python 3.11 requirements, and smoke-tested imports for `run_validation`, `run_reports`, and `run_dciodvfy`.
- Installed IBM Aspera Desktop; `ascp -A` reported version `4.4.7.2245`.
- Re-ran real preflight: 7/10 required checks ready, blocked only on MIDI-B corpus, MIDI-B answer key, and real blinded reviewers.
- Confirmed remaining missing-resource behavior must be recorded rather than simulated.

## Required User Action

Provide the missing resources through secure local paths, environment variables, mounted approved storage, authorized repositories, protected reviewer workstations, or approved secret stores. Do not paste secrets, PHI, reviewer identity mappings, signing keys, or institutional endpoint tokens into chat or source files.
