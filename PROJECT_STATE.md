# PROJECT_STATE

## Project Overview

### Project Name

DICOM Privacy Auditor

### Goal

Complete every locally possible validation/release/demo task while preserving the external-validation claim boundary.

### Current Status

Local v0.7.2 release gate passed, final validation evidence was packaged, synthetic demo screenshots/video were captured, real public external sources were acquired/executed where possible, and the project was prepared for publication under `AKaturu/dicom-privacy-auditor`. The real external preflight is now 7 of 10 required checks ready. Full external validation remains blocked because the actual MIDI-B DICOM corpus, MIDI-B answer-key database, independent reviewers, institutional authorization, native runners, and signing credentials were not supplied.

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

Orthanc `orthancteam/orthanc:26.6.0` was pulled and run locally with HTTP, DIMSE, and DICOMweb probes passing. The synthetic benchmark was executed through the Orthanc adapter and through RSNA DicomAnonymizerTool DAT from the RSNA legacy downloads. Public TCIA MIDI-B manifests and mapping CSVs were downloaded and hashed, CBIIT `MIDI_validation_script` was cloned and smoke-tested with its Python dependencies, Python 3.12 plus `rsna-anonymizer` 18.0.7 were installed and smoke-tested, IBM Aspera `ascp` was installed, and the real-source preflight improved to 7 of 10 required checks ready. Evidence is under `validation/codex/external`.

#### Tests Added

No source tests added; external-source evidence was validated through benchmark runs, evaluator outputs, public preflight JSON, source hashes, and artifact/path-leak checks.

### Synthetic-First GitHub Data Policy

#### Validation

README and docs now make the public GitHub path synthetic-first: demos, screenshots, videos, examples, and tests use generated synthetic DICOM data. Real MIDI-B or institutional data remains supported only as a governed local workflow documented in `docs/REAL_DATA_SETUP.md`.

#### Tests Added

No source tests added; documentation links, ignore rules, and claim boundaries were validated with text searches and git status checks.

### GitHub Publication Prep

#### Validation

GitHub owner metadata, CODEOWNERS, citation metadata, and security documentation now point at `AKaturu/dicom-privacy-auditor`. Pytest uses a repository-local temporary directory for clean clone/Windows reliability, GitHub workflows explicitly load `pytest-cov` while plugin autoload is disabled, and Windows path handling was hardened in evidence archive verification plus documentation checking.

#### Tests Added

Validated with Ruff, Ruff format check, mypy, targeted regression tests, and the full suite: `163 passed, 7 skipped`, coverage `85.75%`.

## Current Work

### Active Feature

GitHub publication.

### Progress

Complete for all tasks possible without private or governed external resources. Public Orthanc and RSNA DAT workflows were executed on synthetic data, real public MIDI-B manifest/mapping files were acquired, official validator/anonymizer command availability is wired into preflight, and the GitHub-facing workflow now defaults clearly to synthetic demonstrations with separate real-data setup instructions. Publication prep has passed local validation and is ready to push to GitHub.

### Remaining Work

Official external validation cannot be marked complete until the missing governed resources are supplied and run according to `STUDY_PROTOCOL.md`.

## Next Actions

1. Download the official MIDI-B DICOM corpus from the acquired TCIA `.tcia` manifests into an approved local path and configure `midi_b_corpus`.
2. Complete the TCIA/Faspex answer-key download through an authenticated bearer-token transfer flow and configure `midi_b_answer_key`.
3. Supply a working RSNA CTP directory pipeline if CTP execution must be claimed; command availability is ready, but pipeline execution is not.
4. Supply independent reviewers/adjudicator, authorized institutional endpoints if applicable, native runner provenance, and signing/notary credentials if trusted signing is desired.
5. Re-run external preflight and only then execute the official campaign and human review.
6. After GitHub upload, confirm Actions status and configure any branch protection/secrets required for release automation.

## Risks

### Open Questions

Which exact external resources, reviewers, and credentials will be supplied by the project owner?

### Known Issues

The final status remains `PARTIALLY COMPLETE - EXTERNAL BLOCKERS REMAIN`. The real public Orthanc, RSNA DAT, CBIIT validator-source, RSNA Python anonymizer, Aspera, and MIDI-B manifest/mapping evidence improves the artifact, but must not be rewritten as official MIDI-B corpus validation or human-reviewed completion.

### Technical Concerns

The Tk desktop UI was not captured because this Windows Python/Tk runtime previously failed headless/local gate plotting with Tcl runtime issues. The Streamlit web UI was captured instead.

## Resume Instructions

Start from the latest commit after the GitHub publication prep update. Review `README.md`, `docs/REAL_DATA_SETUP.md`, `docs/DEMO.md`, `validation/codex/final/FINAL_VALIDATION_REPORT.md`, `validation/codex/demo/media/DEMO_CAPTURE_REPORT.md`, `validation/codex/external/REAL_EXTERNAL_SOURCES_REPORT.md`, `validation/codex/external/MIDI_B_PUBLIC_RESOURCE_INVENTORY.json`, and `validation/codex/external-preflight-real-public.json` before making any external-validation claim changes.
