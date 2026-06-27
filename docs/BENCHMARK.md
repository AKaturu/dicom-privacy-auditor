# Synthetic Benchmark Design

## Purpose

The benchmark measures workflow-level removal of known artificial identifiers and the ability of the auditor to detect residual synthetic leakage. It contains no real protected health information.

## Experimental unit

The primary experimental unit is one injected identifier instance. Each injected case contains one target injection so that failure attribution is unambiguous. Clean controls contain no injected identifier.

## Strata

| Stratum | Example target | Residual rule |
|---|---|---|
| Standard metadata | `PatientName`, `PatientID`, `AccessionNumber` | Exact artificial token remains anywhere in the candidate dataset |
| Nested sequence | `RequestAttributesSequence` item | Exact artificial token remains anywhere in recursive content |
| Private attribute | Private creator block value | Exact artificial token remains in a private or public element |
| Free text | Email, telephone, labeled MRN, person name | Exact artificial text remains |
| Filename | Artificial name token | Token remains in output filename |
| Temporal | Study/series/acquisition/content date | Original synthetic date remains |
| UID | Study, series, frame, or SOP instance UID | Original synthetic UID remains |
| Pixel annotation | Rendered synthetic MRN | Source and output region retain high correlation and local contrast |
| Overlay graphics | Group 6000 overlay data | Artificial overlay payload remains in `OverlayData` |
| File Meta Information | Source Application Entity Title | Exact artificial token remains in File Meta Information |
| Preamble | Artificial ASCII preamble token | Token remains in the first 128 bytes |

## Reproducibility

Generation is controlled by:

- benchmark version;
- manifest schema version;
- random seed;
- cases per stratum;
- number of clean controls; and
- deterministic UID derivation.

The manifest stores every artificial value, SHA-256 digest, expected path, and pixel bounding box when applicable.

## Positive and negative controls

The no-op pipeline should leave all identifiers. The benchmark-aware baseline should remove all target identifiers. A metadata-only comparator should fail filename and pixel strata. Deviations indicate a benchmark or evaluator regression.

## Pixel method

Synthetic text is rendered into an uncompressed 8-bit monochrome image. The manifest records the bounding rectangle. Residual status is based on normalized patch correlation and remaining local contrast. This method is designed to evaluate the known synthetic insertion, not to solve general burned-in-text detection.

## Workflow-level filename interpretation

A tool invoked with a caller-selected safe output filename may appear to remove filename leakage even if the tool does not manage filenames itself. The run manifest therefore records the adapter's output-name policy. Publication tables should report whether filename cleaning was native to the tool, performed by a wrapper, or imposed by the benchmark adapter.

## Failure handling

Missing or unreadable outputs are treated conservatively as unsuccessful removal for injected identifiers. DICOM readability and basic consistency are reported separately from privacy performance.

## Planned extensions

- Multi-frame and compressed transfer syntaxes
- Structured reports and presentation states
- Advanced graphics beyond the initial overlay-data stratum
- Encapsulated PDF/CDA content
- DICOMDIR and companion-manifest leakage
- Cross-object UID consistency
- Clinical-utility preservation metrics
- Multi-vendor external validation
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
