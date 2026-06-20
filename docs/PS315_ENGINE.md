# DICOM PS3.15 policy engine

## Scope and distribution model

Version 0.6.1 retains the complete PS3.15 policy-engine capability but no longer bundles the DICOM Standard, the official Part 15 DOCX, or complete extracted copies of Tables E.1-1 and E.1-2.

Users generate a private local rule cache from an official document they obtain from DICOM/NEMA. The project can either:

- Parse a user-supplied official Part 15 DOCX; or
- Download the current official DOCX to a temporary directory, parse it locally, and delete the temporary DOCX after generation.

The generated JSON files are written outside the package by default:

- Linux: `~/.local/share/dicom-privacy-auditor/ps315`
- macOS: `~/Library/Application Support/DICOMPrivacyAuditor/ps315`
- Windows: `%LOCALAPPDATA%\DICOMPrivacyAuditor\ps315`

Override the location with `DICOM_PRIVACY_PS315_DATA_DIR` or the CLI `--data-dir` option. Select a generated edition with `DICOM_PRIVACY_PS315_EDITION` or `--edition`.

## Prepare the local rule cache

Install the parser dependency:

```bash
pip install "dicom-privacy-auditor[standards]"
```

Temporarily download the official current DOCX and generate local tables:

```bash
dicom-privacy-ps315 --edition 2026c prepare-data --download
```

Or use a document you obtained separately:

```bash
dicom-privacy-ps315 --edition 2026c prepare-data \
  --source /path/to/part15.docx
```

Choose an explicit local output directory:

```bash
dicom-privacy-ps315 \
  --edition 2026c \
  --data-dir /secure/local/standards-cache \
  prepare-data \
  --source /path/to/part15.docx
```

The generator verifies that the requested edition marker is present and records the source SHA-256 in the local outputs. It does not copy the source DOCX into the output directory.

## Commands

Inspect installation status and provenance:

```bash
dicom-privacy-ps315 info --json
```

Before local data is prepared, `info` remains usable and reports `"installed": false` with setup instructions. Rule queries and evaluations fail with an actionable message rather than silently using incomplete fallback data.

Query an attribute rule:

```bash
dicom-privacy-ps315 rules --tag 00100010
dicom-privacy-ps315 rules --name "Study Instance UID" --option retain_uids
```

Query coded Structured Report content:

```bash
dicom-privacy-ps315 codes --scheme DCM --code 121022 --value-type TEXT
```

Evaluate a source/output pair:

```bash
dicom-privacy-ps315 evaluate source.dcm candidate.dcm \
  --option clean_descriptors \
  --option retain_longitudinal_modified_dates \
  --json ps315-evaluation.json \
  --csv ps315-evaluation.csv
```

Allow-list a reviewed private attribute only when the Retain Safe Private Option is active:

```bash
dicom-privacy-ps315 evaluate source.dcm candidate.dcm \
  --option retain_safe_private \
  --safe-private-tag 00191010
```

## Supported profile options

- Retain Safe Private
- Retain UIDs
- Retain Device Identity
- Retain Institution Identity
- Retain Patient Characteristics
- Retain Longitudinal Temporal Information with Full Dates
- Retain Longitudinal Temporal Information with Modified Dates
- Clean Descriptors
- Clean Structured Content
- Clean Graphics
- Clean Pixel Data
- Clean Recognizable Visual Features

The first ten options are resolved directly against the locally generated Table E.1-1 data. Coded-content rules are resolved against locally generated Table E.1-2 data. Pixel and recognizable-feature options generate operational review checks because their success cannot be established solely from an attribute table.

## Action interpretation

The evaluator recognizes the profile action vocabulary used by the tables:

- `X`: remove the attribute
- `Z`: retain the attribute at zero length
- `D`: replace with a non-zero dummy value
- `K`: retain the source value
- `C`: clean identifying content while preserving non-identifying content
- `U`: replace a UID while maintaining internal consistency

Composite directives are preserved. When multiple selected options impose different directives, the engine reports the conflict and requests review rather than inventing undocumented precedence.

## Evaluation behavior

- Recursively traverses nested sequences using stable item paths.
- Applies the private-attribute rule to odd-group attributes.
- Flags candidate-introduced private or other non-empty attributes when all active directives permit only removal or zero length.
- Checks repeated UID replacements for internal consistency.
- Checks Media Storage SOP Class/Instance UIDs against the candidate dataset.
- Applies locally generated coded-content rules to matching Structured Report content items.
- Redacts source and candidate paths by default.

## Boundaries

This is a standards-based policy evaluator, not a DICOM conformance certificate.

- It does not implement a complete IOD/type/conditional validator.
- A changed value can satisfy the structural portion of `C`, but semantic cleanliness still requires human or domain-specific review.
- Pixel cleaning, graphics cleaning, and recognizable-feature removal require visual or algorithmic review.
- Safe-private allow-lists must be externally governed and vendor/version specific.
- New DICOM editions may add or revise rules; analyses should record the locally generated edition and source checksum.
- Locally generated complete tables are not covered by this project's MIT license and should not be redistributed without reviewing applicable NEMA/DICOM terms.

## Official source

The default download endpoint is:

```text
https://dicom.nema.org/medical/dicom/current/output/docx/part15.docx
```

See [Legal notices](LEGAL_NOTICES.md).

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved.
