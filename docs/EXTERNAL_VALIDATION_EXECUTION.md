# External validation execution

Version 0.6.5 provides a preflight that turns the remaining external dependencies into a machine-readable go/no-go report.

```bash
dicom-privacy-external configs/external-validation.example.json --output validation/live/external-preflight.json
```

A `ready` result means only that configured resources were found or reached. It does not establish clinical safety, regulatory compliance, institutional authorization, reviewer independence, or successful MIDI-B performance.

## Required evidence

1. Preserve the exact MIDI-B distribution checksum and answer-key checksum.
2. Freeze Orthanc, RSNA Anonymizer, and CTP versions or container digests.
3. Save raw official-validator output before normalization.
4. Keep blinded reviewer packets separate from adjudication and identity keys.
5. Record PACS/DICOMweb authorization, endpoint type, software version, and a non-PHI test-study identifier.
6. Retain GitHub Actions provenance, checksums, SBOMs, and signing/notarization logs for each native artifact.

## Review design

Use at least two independent reviewers, mask tool identity and expected answer, include negative controls, and resolve disagreements through a separately documented adjudication step. Do not claim independent blinded review when the same developer creates, reviews, and adjudicates the cases.

## v0.6.6 configuration hardening

The preflight configuration is validated against `external-validation-config.schema.json`; unknown keys and invalid ports, timeouts, environment-variable names, and check names are rejected. Mark resources that are intentionally deferred in `optional_checks`. A `ready` result then means every *required* check passed, while optional blockers remain visible in the report.

Set `fingerprint_resources` to `true` to record SHA-256 hashes for files and executables. MIDI-B directories receive an inventory fingerprint over sorted relative paths and file sizes so preflight remains practical for very large corpora; this is not a byte-level corpus hash. For authenticated HTTP endpoints, set `http_auth_environment_variable` to the name of an environment variable containing the complete Authorization header value. The secret is used in memory and is never written to the report.


## v0.6.7 provenance locking

Set `fingerprint_mode` to `inventory` for a fast path-and-size fingerprint or `content` for a byte-level identity over every corpus file. Content mode is slower but detects same-size byte changes. Create a portable lockfile with `--write-lock resource-lock.json`, and verify a later environment with `--verify-lock resource-lock.json`; drift exits with status 4. Lockfiles contain fingerprints and a sanitized configuration digest, not local paths, commands, credentials, or authorization values. Use `--redact-paths` when preserving the preflight report outside the validation environment. Authenticated HTTP probes now require HTTPS to prevent accidental credential transmission over plaintext transport.

## v0.7.0 local-completion boundary

Version 0.7.0 adds a separate local release gate, deterministic migration bundle, stricter HTTP and UID validation, schema/configuration synchronization, dependency-lock checks, and formal reviewer disagreement packets. These controls make external runs more reproducible and easier to audit, but they do not convert resource readiness into performance evidence. Preserve the preflight report, resource lock, exact tool outputs, adjudication packet, evidence archive, and platform signature-status records together.
