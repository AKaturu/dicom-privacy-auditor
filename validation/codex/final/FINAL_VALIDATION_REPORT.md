# Final Validation Report

Status: `PARTIALLY COMPLETE - EXTERNAL BLOCKERS REMAIN`

Generated UTC: `2026-06-20T22:24:18.001211+00:00`

Release under validation: `dicom-privacy-auditor` `0.7.2`

Validated source commit: `a37f7e402c03513f717e7baecfe1d6f63e85230a`

## Executive Result

All work possible in the supplied environment was completed. The local release gate passed for the patched v0.7.2 source tree, the v0.7.2 wheel/source artifacts were rebuilt and checked, and a redacted external preflight was executed with a verified resource lock.

The full external study is not complete because required real resources were unavailable. No MIDI-B performance, official-validator parity, live Orthanc/RSNA/CTP workflow result, independent human-review result, institutional PACS/DICOMweb result, native GitHub runner result, trusted signing result, notarization result, clinical-safety claim, regulatory claim, HIPAA/GDPR compliance claim, or DICOM PS3.15 certification claim is made.

## Post-Release External Evidence Addendum

On 2026-06-21 UTC, additional real public-source work improved the external preflight from the original package-era `1/10` required checks ready to `7/10` required checks ready. The current addendum is recorded in `validation/codex/external/REAL_EXTERNAL_SOURCES_REPORT.md`, `validation/codex/external/REAL_EXTERNAL_SOURCES_RECORD.json`, `validation/codex/external/MIDI_B_PUBLIC_RESOURCE_INVENTORY.json`, and `validation/codex/external-preflight-real-public.json`.

The remaining required blockers are the actual MIDI-B DICOM corpus, the MIDI-B answer-key database, and two real blinded reviewers. The packaged v0.7.2 release artifacts listed below were not rebuilt by this addendum.

## Completed Commands And Results

| Command | Result | Evidence |
|---|---|---|
| Verify supplied v0.7.1 handoff archive and manifests | passed | original handoff SHA-256 and manifest verification |
| `git init` and initial import commit | passed | `ca844d01db3360386467b00f65742494b564648a` |
| `python scripts/run_local_release_gate.py . --output validation/codex/baseline/local-release-gate.json` | final run passed | `validation/codex/baseline/local-release-gate.json` |
| `python -m ruff check .` | passed | local gate `ruff` check |
| `python -m mypy` | passed | local gate `mypy` check |
| `python -m pytest` with coverage | passed | local gate `tests-and-coverage`; 163 passed, 7 skipped, 85.75% coverage |
| `dicom-privacy-external validation/codex/external-validation.json --output validation/codex/external-preflight-private.json --write-lock validation/codex/external-resources.lock.json` | blocked as expected because resources were not configured | `validation/codex/external-preflight-private.json` |
| `dicom-privacy-external validation/codex/external-validation.json --output validation/codex/external-preflight-public.json --redact-paths --verify-lock validation/codex/external-resources.lock.json` | blocked; lock verified | `validation/codex/external-preflight-public.json` |
| `python scripts/build_release_distributions.py . --output validation/codex/release/python --clean` | passed | v0.7.2 wheel and sdist |
| `python scripts/package_source_release.py . --output validation/codex/release/dicom-privacy-auditor-v0.7.2-source.zip` | passed | v0.7.2 source ZIP |
| `python scripts/check_distribution_contents.py . validation/codex/release` | passed | no prohibited standards, credentials, keys, databases, or unsafe archive content found |
| `python scripts/generate_runtime_sbom.py . --output validation/codex/release/SBOM-runtime.cdx.json` | passed | runtime CycloneDX SBOM |
| `python scripts/assemble_release_bundle.py ...` | passed | `validation/codex/release/dicom-privacy-auditor-v0.7.2-codex-release-bundle.zip` |

## Local Release Gate

- Status: `passed`
- Release: `0.7.2`
- Started UTC: `2026-06-20T22:12:51.483301+00:00`
- Finished UTC: `2026-06-20T22:14:47.867386+00:00`
- Failed checks: none
- Checks: action-pins=passed, workflow-yaml=passed, schema-integrity=passed, dependency-locks=passed, installed-dependencies=passed, ruff=passed, ruff-format=passed, compileall=passed, documentation=passed, mypy=passed, bandit-medium-high=passed, tests-and-coverage=passed, build=passed, distribution-policy=passed, package-metadata=passed, clean-wheel-smoke=passed, reproducible-distributions=passed

## External Preflight

- Status: `blocked`
- Required ready: `1/10`
- Resource lock status: `verified`
- Resource lock fingerprints verified: `0`

Missing required checks:

- midi_b_corpus (not configured)
- midi_b_answer_key (not configured)
- official_validator (not configured)
- rsna_anonymizer (not configured)
- rsna_ctp (not configured)
- orthanc_http (not configured)
- orthanc_dimse (host/port not configured)
- dicomweb (not configured)
- blinded_reviewers (configured reviewers: 0)

## Code Changes

- Bumped release metadata from v0.7.1 to v0.7.2 because source changes were required.
- Fixed Windows-only mypy handling for the Tk desktop folder opener.
- Fixed external-validator executable lookup for quoted Windows commands.
- Isolated clean-wheel smoke testing from inherited user/site Python state and installed core runtime dependencies in the smoke venv.
- Forced publication and benchmark plotting through Matplotlib `Agg` for headless/local gate execution.
- Adjusted Windows portability tests for NTFS/account permission behavior.
- Pruned `validation/codex` from source distributions and source release ZIPs.

## Final Artifacts

Canonical checksums for all final deliverables are in `SHA256SUMS.txt`.

- `SBOM-runtime.cdx.json`: `3101ef046060e03b64daebfb2761ce0aae4ae736d26f846f23410db8f587e3af` (SBOM, 115413 bytes)
- `dependency-versions.txt`: `187f3322d206620f5a913f33ef2a5796c7d22d8333dcd3ac6f7ea9aa44d441fe` (dependency record, 2348 bytes)
- `dicom-privacy-auditor-v0.7.2-codex-release-bundle.zip`: `e7cc736896fb34a25af10e86241c221346a4631b5d7d65421a0e677a43956889` (release bundle, 1171888 bytes)
- `dicom-privacy-auditor-v0.7.2-source.zip`: `5cad7d3031b807465ecdeb0d7eda34af8f1bf34775762ef9a315585525967d2c` (source archive, 745111 bytes)
- `dicom_privacy_auditor-0.7.2-py3-none-any.whl`: `43ba9a49ee2f008ea42be01f7f54e9a95b4c3e8d199a7ac503019d95093f0b58` (wheel, 175368 bytes)
- `dicom_privacy_auditor-0.7.2.tar.gz`: `4ea5ab52da8e3488521977a2c7dd7de6a1b9427959d77039de286e6cc23063d7` (sdist, 264184 bytes)
- `environment.json`: `47d0dc4a0b24b429936ba5939e6fc1b9695d1d1744a0dd6ab6976a91d8cecbf3` (environment record, 1864 bytes)
- `external-preflight-public.json`: `350adb4507cb5418d51f2eb8492e096e52f4860ccfb52c7d3cf1abae8bbd23ff` (external preflight evidence, 2298 bytes)
- `external-resources.lock.json`: `42b3965cb94388525e4a36607faec412c702876787b769cfef2d323dedd6cdeb` (resource lock, 153 bytes)
- `local-release-gate.json`: `c296042b2a57e8ddf443eda042cadfdaea4a17c0bf96f9ff5c16c257a8a1355d` (release gate evidence, 40846 bytes)

## Unresolved Discrepancies

- No official-validator parity discrepancies were produced because the official MIDI-B validator and MIDI-B corpora were not supplied.
- No human-review disagreements were produced because independent reviewers and an adjudicator were not supplied.
- No live Orthanc, RSNA Anonymizer, RSNA CTP, additional workflow, institutional endpoint, native runner, signing, or notarization discrepancies were produced because those resources were not supplied.

## Claim Limitation

This package demonstrates local software readiness and honest external-resource blocking behavior only. It is not a publication-complete external validation, clinical deployment approval, regulatory certificate, or privacy-law compliance certificate.
