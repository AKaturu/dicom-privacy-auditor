# DICOM Privacy Auditor 0.7.2

Version 0.7.2 is a validation-driven patch release. It fixes Windows mypy validation for the Tk desktop folder opener and keeps the external-validation claim boundary unchanged.

## Claim boundary

This release remains a research alpha and does not claim full MIDI-B execution, official-validator parity, institutional validation, independent review, trusted cross-platform signing, clinical safety, or regulatory compliance.

# DICOM Privacy Auditor 0.7.1

Version 0.7.1 is the final local adversarial-testing and installation-integrity release. It adds property-based malformed-DICOM testing, hostile archive defenses, crash-safe evidence writes, clean-wheel entry-point verification, documentation checks, and package-metadata validation.

## Local validation

- 169 automated tests pass with 85.96% measured core coverage and an 85% gate.
- Hypothesis exercises arbitrary byte streams and generated nested DICOM datasets.
- Evidence archives reject traversal, drive-qualified paths, normalized dot paths, duplicate separators, links, devices, and FIFOs.
- Atomic write tests verify that interrupted replacements preserve the previous valid file and remove temporary files.
- The built wheel is installed outside the source tree and all 18 console entry points are smoke-tested.
- Twine metadata, Markdown links, Ruff, formatting, mypy, schemas, workflows, dependency locks, action pins, and distribution policy pass.

## Claim boundary

This release remains a research alpha and does not claim full MIDI-B execution, official-validator parity, institutional validation, independent review, trusted cross-platform signing, clinical safety, or regulatory compliance.

# DICOM Privacy Auditor 0.7.0

Version 0.7.0 is the local-completion and release-integrity milestone. It consolidates the 0.6.x work and completes every validation, security, reproducibility, packaging, and Linux-native task that can be executed in the current environment without the external MIDI-B distribution, live third-party installations, institutional authorization, independent reviewers, target-platform runners, or owner-controlled signing credentials.

## Local validation

- 145 automated tests pass with 82.34% measured coverage and the 82% gate satisfied.
- Ruff lint and formatting, mypy, Bandit medium/high, schema/configuration integrity, dependency-lock consistency, workflow parsing, immutable action pins, compile checks, and `pip check` pass.
- Wheel and normalized source distribution builds are byte-for-byte reproducible.
- Source and release bundles are deterministic and protected by SHA-256 manifests.
- Privacy-bearing outputs use owner-only permissions by default.
- Distribution scanning rejects copyrighted standards source files, credentials, private keys, databases, unsafe/duplicate archive members, links, and excessive declared sizes.
- The exact Linux x86-64 CLI and desktop applications are rebuilt and smoke-tested as part of the final release process.

## Correctness and security fixes

- Migrated MIDI-B campaigns now score against the relocated source root rather than the stale import path.
- Benchmark, campaign, study, corpus, IOD-registry, and evidence workflows reject traversal, root overlap, symlink escape, duplicate records, malformed checkpoints, and unbounded hostile inputs.
- Official-validator execution has a configurable timeout and structured timeout results.
- Evidence archives are deterministic, bounded, atomic, independently verifiable, and cannot include themselves.
- Publication packages redact operational paths unless `--disclose-paths` is explicitly requested.
- External-resource lockfiles and content fingerprints detect corpus, answer-key, executable, and configuration drift.
- External-tool adapters bound source and produced-object sizes, reject linked or overlapping transfer paths, write owner-only destinations atomically, and remove transient watched-directory outputs by default after a verified copy.

## Claim boundary

This release does not claim a completed full MIDI-B run, official-validator parity result, live Orthanc/RSNA result, blinded independent review, institutional PACS/DICOMweb validation, trusted Windows/macOS signing, or clinical/regulatory suitability. The repository contains the execution, preflight, review, parity, evidence, and cross-platform CI workflows needed to complete those tasks when the required outside resources are supplied.

# DICOM Privacy Auditor 0.6.7

External-validation provenance release. Adds byte-level corpus identity, portable resource lockfiles, deterministic drift checks, redacted preflight output, and an HTTPS requirement for authenticated endpoint probes.

## Claim boundary

This release verifies software behavior and provenance controls locally. It does not claim that the full MIDI-B corpus, official validator, RSNA tools, institutional systems, independent reviewers, or signed Windows/macOS release artifacts were available or executed.

# v0.6.4

Evidence-integrity hardening release. Adds `campaign verify-evidence` and `campaign archive-evidence`, deterministic evidence archives, safe archive verification, and broader operational-path redaction. External MIDI-B, live-tool, institutional, reviewer, and non-Linux validations remain unclaimed.

# DICOM Privacy Auditor 0.6.3

Version 0.6.3 completes additional local publication-readiness work. It creates deterministic review samples, compares normalized official and internal action-level evaluations, and assembles redacted evidence packages with SHA-256 manifests.

## New commands

```bash
dicom-privacy-campaign review-sample evaluation.json review-sample.json \
  --failures-per-stratum 25 --controls-per-stratum 10 --seed 20260620

dicom-privacy-campaign parity internal.json official-normalized.json parity-report.json

dicom-privacy-campaign evidence-package workspace validation/live/campaign-id \
  --campaign-id campaign-id --overwrite
```

## Claim boundary

This release does not claim execution of the complete MIDI-B collections, live Orthanc or RSNA tools, independent blinded review, institutional DICOMweb validation, or official-validator agreement. It supplies reproducible tooling to record those results once external resources are available.
