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
- Evidence: failed local gate attempts preserved locally under `validation/codex/baseline/`.

## D-003: External campaign phases blocked

- Status: blocked
- Description: Required external corpora, official validator, live tools, reviewers, institutional authorization, native runners, and signing credentials were not supplied.
- Resolution: Per protocol, no external performance, review, institutional, signing, or notarization claims are made.
- Evidence: `validation/codex/RESOURCE_STATUS.md`, `validation/codex/BLOCKERS.md`, `validation/codex/external-preflight-public.json`

## D-004: Public archive excludes raw failed local-gate tails

- Status: redaction decision
- Description: Failed local-gate attempts are preserved locally as raw evidence but contain workstation path fragments emitted by tools.
- Resolution: The public final archive includes the final passing gate and validation summaries, while raw failed attempts remain in the local validation workspace.
