# PROJECT_STATE

## Project Overview

### Project Name

DICOM Privacy Auditor

### Goal

Complete every locally possible validation/release/demo task while preserving the external-validation claim boundary.

### Current Status

Local v0.7.2 release gate passed, final validation evidence was packaged, and synthetic demo screenshots/video were captured. External blockers remain because real corpora, official tools, independent reviewers, institutional authorization, native runners, and signing credentials were not supplied.

## Completed Features

### v0.7.2 Portability Release

#### Validation

Full local release gate passed at `validation/codex/baseline/local-release-gate.json`.

#### Tests Added

Windows portability tests were adjusted for filesystem permission and symlink behavior; packaging tests cover source archive pruning.

### Final Validation Evidence

#### Validation

Final records, resource provenance, SBOM, checksums, release bundle, and final evidence archive were generated under `validation/codex/final` and copied to `outputs/`.

#### Tests Added

No new tests; release artifacts were verified with checksum, archive, content-policy, and path-leak checks.

### Synthetic Demo Media

#### Validation

`dicom-privacy-demo` generated a synthetic demo workspace. Streamlit was launched locally and captured with Playwright as screenshots plus a WebM walkthrough. Demo media artifacts are under `validation/codex/demo/media` and copied to `outputs/`.

#### Tests Added

No source tests added; media was validated with nonblank image checks, video metadata inspection, checksum verification, ZIP inspection, and path-leak scanning.

## Current Work

### Active Feature

None.

### Progress

Complete for all tasks possible without external resources.

### Remaining Work

External validation cannot be marked complete until the missing real resources are supplied and run according to `STUDY_PROTOCOL.md`.

## Next Actions

1. Supply official MIDI-B collections, answer keys, mappings, and validator through approved secure local paths.
2. Supply pinned Orthanc/RSNA/CTP resources and configurations, independent reviewers/adjudicator, authorized institutional endpoints if applicable, native runner provenance, and signing/notary credentials if trusted signing is desired.
3. Re-run external preflight and only then execute the live campaign and human review.

## Risks

### Open Questions

Which exact external resources, reviewers, and credentials will be supplied by the project owner?

### Known Issues

The final status remains `PARTIALLY COMPLETE — EXTERNAL BLOCKERS REMAIN`. This must not be rewritten as complete without actual external evidence.

### Technical Concerns

The Tk desktop UI was not captured because this Windows Python/Tk runtime previously failed headless/local gate plotting with Tcl runtime issues. The Streamlit web UI was captured instead.

## Resume Instructions

Start from commit `bf3cd86` plus the demo-media commit after this file is committed. Review `validation/codex/final/FINAL_VALIDATION_REPORT.md` and `validation/codex/demo/media/DEMO_CAPTURE_REPORT.md` before making any external-validation claim changes.
