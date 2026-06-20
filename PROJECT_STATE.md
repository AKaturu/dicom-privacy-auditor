# PROJECT_STATE

## Project Overview

### Project Name

DICOM Privacy Auditor

### Goal

Complete every locally possible validation/release/demo task while preserving the external-validation claim boundary.

### Current Status

Local v0.7.2 release gate passed, final validation evidence was packaged, synthetic demo screenshots/video were captured, and real public external sources were acquired/executed where possible. Full external validation remains blocked because official MIDI-B resources, official scoring/validator access, independent reviewers, institutional authorization, native runners, and signing credentials were not supplied.

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

### Real External Sources Addendum

#### Validation

Orthanc `orthancteam/orthanc:26.6.0` was pulled and run locally with HTTP, DIMSE, and DICOMweb probes passing. The synthetic benchmark was executed through the Orthanc adapter and through RSNA DicomAnonymizerTool DAT from the RSNA legacy downloads. The real-source preflight remains blocked at 4 of 10 required checks ready; evidence is under `validation/codex/external`.

#### Tests Added

No source tests added; external-source evidence was validated through benchmark runs, evaluator outputs, public preflight JSON, source hashes, and artifact/path-leak checks.

## Current Work

### Active Feature

None.

### Progress

Complete for all tasks possible without private or governed external resources. Public Orthanc and RSNA DAT workflows were executed on synthetic data.

### Remaining Work

Official external validation cannot be marked complete until the missing governed resources are supplied and run according to `STUDY_PROTOCOL.md`.

## Next Actions

1. Supply official MIDI-B collections, answer keys, mappings, and validator through approved secure local paths with enough disk space for the TCIA downloads.
2. Supply modern RSNA Anonymizer Python 3.12 runtime/configuration and a working RSNA CTP directory pipeline if those tools must be in scope.
3. Supply independent reviewers/adjudicator, authorized institutional endpoints if applicable, native runner provenance, and signing/notary credentials if trusted signing is desired.
4. Re-run external preflight and only then execute the official campaign and human review.

## Risks

### Open Questions

Which exact external resources, reviewers, and credentials will be supplied by the project owner?

### Known Issues

The final status remains `PARTIALLY COMPLETE - EXTERNAL BLOCKERS REMAIN`. The real public Orthanc and RSNA DAT evidence improves the artifact, but must not be rewritten as official MIDI-B or human-reviewed completion.

### Technical Concerns

The Tk desktop UI was not captured because this Windows Python/Tk runtime previously failed headless/local gate plotting with Tcl runtime issues. The Streamlit web UI was captured instead.

## Resume Instructions

Start from the latest commit after the real external-source addendum. Review `validation/codex/final/FINAL_VALIDATION_REPORT.md`, `validation/codex/demo/media/DEMO_CAPTURE_REPORT.md`, and `validation/codex/external/REAL_EXTERNAL_SOURCES_REPORT.md` before making any external-validation claim changes.
