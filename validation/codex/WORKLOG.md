# Codex Validation Worklog

## 2026-06-20

- Verified outer handoff archive SHA-256 against the supplied handoff checksum.
- Extracted the v0.7.1 handoff into an isolated workspace.
- Verified every file in `HANDOFF_SHA256SUMS.txt`.
- Verified release artifacts in `artifacts/SHA256SUMS-v0.7.1.txt`.
- Read the required handoff, protocol, external-validation, MIDI-B, human-review, executable, definition-of-done, and external-resource documents.
- Initialized Git for the extracted `project/` tree and committed the verified imported handoff as `ca844d01db3360386467b00f65742494b564648a`.
- Created a Python 3.11.9 virtual environment and installed project validation dependencies.
- Ran the unchanged local release gate to `validation/codex/baseline/local-release-gate.json`; preserved failed attempts before reruns.
- Diagnosed baseline failures as Windows/environment and reproducible portability defects.
- Applied a patch release bump to 0.7.2 because source changes were required.
- Fixed Windows mypy handling for the Tk desktop folder opener.
- Fixed external-validator quoted command handling on Windows.
- Fixed clean-wheel smoke isolation and core dependency installation.
- Forced Matplotlib publication/benchmark plots to use the non-GUI `Agg` backend.
- Adjusted Windows tests so POSIX-only permission and symlink expectations remain active where supported and skip where NTFS or account privileges do not support them.
- Pruned `validation/codex` from source distributions so local validation evidence is not packaged into release artifacts.
- Re-ran the full local release gate successfully with status `passed` and no failed checks.

## Evidence

- `validation/codex/baseline/local-release-gate.initial-failed.json`
- `validation/codex/baseline/local-release-gate.rerun-failed.json`
- `validation/codex/baseline/local-release-gate.third-failed.json`
- `validation/codex/baseline/local-release-gate.json`

## Claim Boundary

No MIDI-B corpus execution, official-validator parity, live Orthanc or RSNA tool campaign, independent blinded review, institutional DICOMweb/PACS validation, native target-runner build, Authenticode signing, or Apple Developer ID notarization was performed in this environment.
