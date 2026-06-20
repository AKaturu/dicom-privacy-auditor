# Changelog

## 0.7.1 - 2026-06-20

- Added Hypothesis property-based testing for arbitrary malformed DICOM byte streams and generated deeply nested datasets.
- Hardened evidence archive validation against Windows drive paths, dot components, doubled separators, traversal, links, devices, and FIFOs.
- Made evidence JSON, status, and checksum writes atomic and owner-only, with simulated-crash recovery tests.
- Added a clean-wheel gate that installs the built wheel outside the source tree and smoke-tests all 18 console entry points.
- Added Twine package-metadata validation and local Markdown-link validation to the unified release gate.
- Raised measured core coverage to 85.96% and the enforced threshold to 85%; the platform GUI shell is excluded from core coverage.
- Expanded the suite to 169 tests.

## 0.7.0 - 2026-06-20

- Completed a repository-wide local hardening pass and resolved all static type errors across the package.
- Added shared HTTP URL validation, redirect refusal, authenticated-transport safeguards, strict DICOM UID validation, bounded standards downloads, and response lifecycle cleanup.
- Added schema mirror/configuration validation, explicit top-level object policies, and tightened adapter, benchmark, study, review, corpus, IOD, publication, and campaign schemas.
- Added reviewer disagreement/adjudication packets, latest-decision semantics, SQLite integrity reporting, owner-only review artifacts, and loopback-only review UI binding by default.
- Hardened benchmark, MIDI-B, study, corpus, IOD-registry, evidence, and campaign filesystem boundaries against traversal, symlink escape, overlapping roots, duplicate records, unsafe archives, and unbounded inputs.
- Fixed migrated MIDI-B evaluation so `--source-root` is used consistently during both processing and scoring.
- Added official-validator timeouts, deterministic resource locks, byte-level corpus fingerprints, evaluator-parity reports, review sampling, and tamper-evident evidence archives.
- Made privacy-bearing CSV, JSON, review, publication, campaign, and evidence outputs owner-only by default; publication paths are redacted unless explicitly disclosed.
- Added dependency-root/hashed-lock consistency checks, `pip check`, Ruff formatting, compile checks, and stricter least-privilege CI permissions to release gates.
- Added deterministic wheel/source-distribution builds, migration-ready source archives, release bundles, and runtime SBOMs with explicit root dependency edges and schema-validated manifests.
- Expanded distribution policy checks to reject standards source documents, credentials, private keys (including inside archives), review databases, duplicate members, links/special files, unsafe paths, and excessive declared archive sizes.
- Hardened native CI signing/notarization handling, signature verification, cleanup, platform-specific status reporting, and least-privilege job permissions.
- Hardened Orthanc, RSNA Anonymizer, and watched-directory adapters with owner-only atomic outputs, bounded input/output copies, symlink and case-ID rejection, watched-root separation, and default cleanup of transient pipeline outputs.
- Added Python 3.13 metadata and expanded regression coverage to 145 tests with an 82% coverage gate.

## 0.6.7 - 2026-06-20

- Added opt-in byte-level corpus fingerprints that detect same-size content changes.
- Added portable external-resource lockfiles and deterministic drift verification.
- Added exit status 4 for resource-lock drift in automated validation workflows.
- Added redacted preflight reports that omit local resource paths and executable locations.
- Required HTTPS whenever an authorization environment variable is used for HTTP probes.
- Added regression tests for byte drift, lock verification, and authenticated transport safety.

## 0.6.4 - 2026-06-20

- Added independent evidence-package checksum verification for directories and tar.gz archives.
- Added safe archive extraction checks and detection of missing, unexpected, malformed, or modified files.
- Added deterministic evidence archive generation with normalized metadata and SOURCE_DATE_EPOCH support.
- Extended evidence redaction to absolute POSIX, UNC, and Windows paths even under unrecognized keys.
- Added regression tests for tampering detection, redaction, archive verification, and byte reproducibility.

## 0.6.3 - 2026-06-20

- Added deterministic, action-stratified human-review sample manifests with failure and negative-control strata.
- Added normalized internal-versus-official evaluator parity reports with discrepancy listings and exact status agreement.
- Added redacted, checksummed campaign evidence-package assembly from run, evaluation, and report JSON outputs.
- Added regression coverage for sampling determinism, evaluator disagreement, path redaction, and evidence checksums.

## 0.6.2 — 2026-06-20

- Added MIDI campaign preflight validation with corpus/action-manifest readiness checks.
- Added `--source-root` overrides so imported MIDI-B manifests remain usable after migration.
- Added deterministic hash-based sharding for large live-tool campaigns.
- Added per-shard append-only checkpoint logs and resume accounting.
- Added finalization of fully assembled sharded outputs before internal/official evaluation.
- Prevented sharded overwrite runs from deleting outputs generated by other shards.

## 0.6.1 — 2026-06-20

- Pinned every GitHub Action to an immutable commit SHA and added a CI pin guard.
- Added a complete SHA-256 runtime lock for CPython 3.13/Linux x86-64.
- Added byte-for-byte reproducible wheel verification.
- Added review database schema version 2, backups, migration ledger, assignments, priorities, and schema CLI commands.
- Added packaged JSON schemas and atomic validation for generated reports.
- Added repeated-page QIDO-RS and malformed-multipart WADO-RS safeguards.
- Added `dicom-privacy-demo` for a complete synthetic demonstration.
- Added `dicom-privacy-report` for CSV/LaTeX tables, manuscript templates, figures, and provenance.
- Completed and smoke-tested the Linux x86-64 CLI and desktop native builds.
- Reduced the native CLI by excluding the separately shipped Tk desktop runtime.
- Made the `native` extra include the PS3.15 parser and DIMSE adapter dependencies required by the advertised CLI commands.
- Expanded the suite to 73 tests and 83.12% measured coverage.

## 0.6.0 — 2026-06-20

### Added

- Blinded human-in-the-loop pixel and metadata review workstation
- Region/frame adjudication, dual-review agreement, Cohen's kappa, and integrity-hashed review exports
- User-local PS3.3-derived IOD registry and IOD-aware PS3.15 evaluation
- Candidate-only invalid-IOD attribute detection and Type 1/1C/2/2C context handling
- Corpus-level UID mapping, UID collision, reference, pseudonym, date-shift, and File Meta checks
- Atomic study processing, resumable checkpoints, and quarantine-by-default incomplete runs
- QIDO-RS, WADO-RS, and STOW-RS client and end-to-end study workflow
- Full-corpus MIDI-B campaign runner for no-op, baseline, Orthanc, RSNA Anonymizer, RSNA CTP, and directory tools
- Reproducibility hashes for application version, tool configuration, campaign definition, and imported MIDI manifest
- JSON schemas and detailed documentation for all new subsystems

### Security and release hardening

- HTTPS/TLS safeguards, environment-based DICOMweb/Orthanc credentials, bounded requests/responses, and redacted error bodies
- CodeQL, dependency review, `pip-audit`, Bandit, Dependabot, and CODEOWNERS
- CycloneDX SBOM generation and GitHub provenance/SBOM attestations for public native releases
- Increased CI coverage threshold to 78%
- Source/candidate values and paths remain redacted or hashed by default in shareable reports

### Validation status

- Expanded automated suite and synthetic/local integration coverage
- Complete official MIDI-B and live Orthanc/RSNA comparative results are not claimed by this source release; the reproducible campaign workflow and live-validation record template are included

## 0.4.1 — 2026-06-20

### Changed

- Removed the Part 15 DOCX and complete extracted E.1-1/E.1-2 JSON tables from public distribution
- Replaced bundled standards data with user-local generation from an official URL or user-supplied DOCX
- Added operating-system data-directory discovery and environment overrides
- Added actionable PS3.15 setup/status reporting when local tables are absent
- Updated native builds to include the parser but not standards content
- Added DICOM trademark and standards-content legal notices

### Safety and release governance

- Added ignore rules and automated tests to prevent accidental redistribution of standards documents/tables
- Clarified MIT license boundaries and project independence from NEMA/DICOM
- Marked v0.4.0 artifacts as unsuitable for public release

## 0.4.0 — 2026-06-19

### Added

- Complete DICOM PS3.15 2026c Table E.1-1 and E.1-2 policy snapshots
- Recursive PS3.15 source/output evaluator and profile-option CLI
- MIDI-B SQLite importer and ten-action evaluator
- Orthanc, RSNA DICOM Anonymizer, RSNA CTP, and directory adapters
- Standards-table regeneration utility
- Adapter, MIDI-B, and PS3.15 documentation and JSON schemas
- Optional pinned Orthanc Docker smoke environment

### Changed

- Version raised to 0.4.0
- Native build now explicitly collects packaged standards data
- Unified executable exposes `ps315`, `midi`, and `adapter` commands
- RSNA Anonymizer headless launch uses `-c ProjectModel.json`

### Safety

- Orthanc `AlreadyStored` uploads are not deleted by default
- Candidate-introduced prohibited private attributes are reported
- File Meta SOP Class/Instance UID consistency is checked

## 0.3.0 — 2026-06-19

### Added

- Double-click Tk desktop auditor with file/folder selection and privacy-safe JSON/CSV reports
- Unified `dicom-privacy` launcher and `DICOMPrivacyAuditor-CLI` native executable
- PyInstaller build and packaging scripts
- Native GitHub Actions matrix for Windows x64, Linux x64, macOS Apple Silicon, and macOS Intel
- Automated native CLI smoke tests, release archives, and SHA-256 checksums
- Draft GitHub Release creation for version tags
- Native distribution and signing/notarization documentation

### Changed

- Version raised to 0.3.0
- Native desktop reports keep source paths and raw values redacted without an unsafe override

### Distribution notes

- Local builds are operating-system specific because PyInstaller is not a cross-compiler
- macOS artifacts are ad-hoc signed but not Apple-notarized
- Windows artifacts are not Authenticode-signed by default


## 0.2.0 — 2026-06-19

### Added

- Deterministic ten-stratum synthetic benchmark
- No-op, metadata-only, and benchmark-aware baseline controls
- External command adapter
- Source-versus-output comparison
- Retained identifier, date, UID, and risky-pixel checks
- File Meta Information and preamble auditing
- Experimental pixel border scan
- DICOM readability and basic consistency validation
- Wilson confidence intervals and exact McNemar comparisons
- Publication-oriented reports and figures
- JSON schemas, Docker, CI, security policy, threat model, and manuscript plan
- Expanded automated test suite

### Changed

- Raw identifier values are redacted and hashed by default
- Expanded metadata, free-text, embedded-content, date, and UID review rules
- Version raised to 0.2.0

### Safety

- The built-in de-identifier is explicitly labeled a research baseline
- Filename adapter behavior is recorded because it changes workflow-level performance

## 0.1.0

- Initial recursive metadata auditor, CLI, Streamlit interface, synthetic examples, exports, and tests
