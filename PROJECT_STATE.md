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

GitHub owner metadata, CODEOWNERS, citation metadata, and security documentation now point at `AKaturu/dicom-privacy-auditor`. Pytest uses a repository-local temporary directory for clean clone/Windows reliability, GitHub workflows explicitly load `pytest-cov` while plugin autoload is disabled, Python 3.10/3.13 CI compatibility was repaired, `pip-audit` skips the editable local project while still auditing dependencies, and Windows path handling was hardened in evidence archive verification plus documentation checking.

#### Tests Added

Validated with `pip-audit --skip-editable --desc on`, Ruff, Ruff format check, mypy, targeted regression tests, and the full suite under pytest 9: `163 passed, 7 skipped`, coverage `85.77%`.

### GitHub Presentation Polish

#### Validation

The README now includes status badges, a repository guide, an explicit quality-gate table, contribution/security links, and package metadata URLs for GitHub, documentation, repository, and issues.

#### Tests Added

No source tests were added; this was documentation and package metadata polish.

### GitHub Demo Media Refresh

#### Validation

Added `scripts/generate_demo_media.py`, `docs/DEMO_MEDIA.md`, and committed synthetic-only poster, GIF, and MP4 assets under `docs/assets/`. The generator runs `dicom-privacy-demo`, reads the real synthetic benchmark summary, and renders GitHub-ready media without committing DICOM objects or generated workspaces.

#### Tests Added

No source tests were added; the media generator is validated by executing it and verifying the generated assets.

#### Follow-up Update

The media generator now renders the complete final frame before encoding, preventing flicker in GitHub GIF/MP4 previews.

### Benchmark Overlay Graphics Roadmap Item

#### Validation

The synthetic benchmark now includes an `overlay_graphics` stratum for group 6000 overlay-data leakage. The evaluator checks whether the artificial overlay payload remains, the auditor detects retained overlay content through embedded-content review findings, and the built-in baseline removes overlay/graphic elements.

#### Tests Added

`tests/test_benchmark.py` now verifies overlay stratum generation. The existing no-op and baseline end-to-end benchmark test covers retained-overlay detection and baseline removal across the expanded stratum set.

## Current Work

### Active Feature

GitHub publication.

### Progress

Complete for all tasks possible without private or governed external resources. Public Orthanc and RSNA DAT workflows were executed on synthetic data, real public MIDI-B manifest/mapping files were acquired, official validator/anonymizer command availability is wired into preflight, and the GitHub-facing workflow now defaults clearly to synthetic demonstrations with separate real-data setup instructions. Publication prep has passed local validation and is ready to push to GitHub. Repository presentation polish has also been completed for the public GitHub page.

Roadmap analysis has started across the GitHub repositories. The first implemented roadmap item is the DICOM Privacy Auditor synthetic benchmark overlay-graphics stratum.

### Benchmark DICOMDIR-Reference Roadmap Item

The synthetic benchmark now includes a `dicomdir_reference` stratum for group 0004 file-set metadata leakage inside ordinary benchmark objects. The evaluator checks retained artificial file-set tokens, the auditor detects group 0004 directory/file-set attributes, and the benchmark-aware baseline removes group 0004 elements.

#### Validation

`tests/test_benchmark.py` now verifies DICOMDIR-reference stratum generation. Full validation passed after installing the local dev test dependencies that were missing in the active interpreter: `python -m pytest -q` and `python -m ruff check src tests docs`.

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
