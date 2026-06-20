# Manuscript Plan

## Working title

**Standards-, benchmark-, corpus-, and human-review evaluation of open-source DICOM de-identification workflows**

## Core question

How reliably do open-source DICOM de-identification workflows complete required privacy actions while preserving readable, internally consistent, and scientifically useful DICOM objects?

## Proposed article type

Imaging-informatics original research or technical development with external benchmark validation.

## Study contribution

The manuscript should not be framed as another de-identification script. Its contribution is a reproducible evaluation system that combines:

- official MIDI-B action-level scoring;
- an independent seeded benchmark;
- source/candidate PS3.15 evaluation with local IOD context;
- collection-wide UID, reference, pseudonym, and date consistency;
- atomic study and DICOMweb workflow accounting; and
- blinded human pixel/metadata adjudication.

## Primary endpoint

MIDI-B required-action accuracy for each frozen workflow on the final test collection.

## Secondary endpoints

- action/category/modality/SOP-class performance;
- residual identifiers and false information destruction;
- unreadable, missing, partial, or quarantined outputs;
- IOD-aware PS3.15 and DICOM validity outcomes;
- corpus-level linkage/reference failures;
- automated-human agreement and review workload;
- runtime and throughput.

## Methods outline

1. Freeze protocol, primary endpoint, tools, configurations, and analysis code.
2. Execute the validation collection to verify integrations without tuning against the test labels.
3. Execute the frozen test collection once for primary analysis.
4. Run the official MIDI-B validator and document parity with the internal evaluator.
5. Apply IOD-aware PS3.15, DICOM validity, and corpus-level checks.
6. Draw a prespecified stratified sample for blinded dual review and adjudication.
7. Report Wilson intervals, exact paired tests, multiplicity handling, and clustered sensitivity analyses.
8. Release code, schemas, non-PHI manifests, configurations, checksums, SBOMs, and provenance records.

## Claims to avoid

- Do not call the software a PS3.15, HIPAA, GDPR, or clinical compliance certificate.
- Do not claim zero residual risk from zero automated findings.
- Do not describe the local IOD registry as a complete PS3.3 validator.
- Do not present the benchmark-aware baseline as deployable or independent.
- Do not call mocked/local protocol tests “live Orthanc/RSNA validation.”
- Do not publish full comparative scores until the complete external collections and frozen live tools have actually run.
- Do not generalize beyond evaluated modalities, SOP classes, manufacturers, transfer syntaxes, and configurations.

## Publication-ready evidence package

```text
validation/live/<campaign-id>/
├── STATUS.md
├── environment.json
├── campaign.json
├── tool-configs-redacted/
├── executable-or-container-digests.json
├── internal-evaluations/
├── official-evaluations/
├── parity-report.json
├── ps315-iod-reports/
├── corpus-reports/
├── review.sqlite.sha256
├── review-export.json
├── deviations.md
└── SHA256SUMS.txt
```

## Current release boundary

Version 0.6.1 supplies the architecture, tests, workflows, schemas, and record templates. It does not contain fabricated full MIDI-B or live external-tool results. Those results must be generated in an environment with the complete collections and dedicated frozen installations.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
