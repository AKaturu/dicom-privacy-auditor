# Protocol Deviations

## D-001: Patch version bump after baseline failure

- Status: accepted
- Description: The v0.7.1 baseline failed on Windows/Python 3.11 because of reproducible portability defects and environment setup issues.
- Resolution: Fixed portability defects and bumped the software version to 0.7.2, as required when source changes are made.
- Evidence: `validation/codex/baseline/local-release-gate.json`

## D-002: Windows temp directory inaccessible

- Status: environment deviation
- Description: The default user temp pytest base was inaccessible to this process.
- Resolution: Used a workspace-controlled temporary directory for repeatable local gate execution.
- Evidence: failed and passing local gate JSON files under `validation/codex/baseline/`.

## D-003: External campaign phases blocked

- Status: blocked
- Description: The actual MIDI-B DICOM corpus, MIDI-B answer-key database, reviewers, institutional authorization, native runners, and signing credentials were not supplied. Public validator/anonymizer/transfer tooling was later acquired and smoke-tested.
- Resolution: Per protocol, no MIDI-B corpus performance, human-review, institutional, signing, or notarization claims are made.
- Evidence: `validation/codex/RESOURCE_STATUS.md`, `validation/codex/BLOCKERS.md`, `validation/codex/external-preflight-real-public.json`
