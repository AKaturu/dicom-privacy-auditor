# Manuscript Plan

## Working Title

**Standards-, benchmark-, corpus-, and reviewer-based evaluation of open-source DICOM de-identification workflows**

## Core Question

How reliably do open-source DICOM de-identification workflows complete required privacy actions while
preserving readable, internally consistent, and scientifically useful DICOM objects?

## Proposed Article Type

Imaging-informatics original research or technical development with external benchmark validation.

## Study Contribution

The contribution is a reproducible evaluation system, not another de-identification script. It combines:

- official MIDI-B action-level scoring;
- an independent strict evaluator and explicit comparator-parity analysis;
- path-aware nested DICOM and PS3.15 evaluation;
- collection-wide UID, reference, pseudonym, and date consistency checks;
- immutable candidate generation, manifests, and provenance; and
- governed AI-assisted and independent-human review fields kept as separate evidence classes.

## Current MIDI-B Technical Result

Version 0.7.2 has a completed MIDI-B Synthetic Validation technical analysis for an immutable,
benchmark-aware baseline candidate:

- 23,921 DICOM instances and 6,173,204 action-level checks;
- zero candidate-generation failures;
- 35 / 35 reviewed pixel regions applied and internally verified;
- 5 / 5 targeted C12 regions with no visible residual lettering on AI technical review;
- 50 / 50 targeted C08/C09 rows reconciled after canonical path and tag-label handling;
- 5,681,593 exact internal/compatibility-patched official matches;
- exact agreement 0.9204 and Cohen's kappa 0.8164;
- internal strict score 0.6464 and compatibility-patched official score 0.7261; and
- four official token-residual failures confirmed by governed recursive DICOM review.

The official comparison used a documented compatibility patch for case-normalized public tag labels.
It is not an unmodified official-validator result. The preserved v1 unmodified result must be reported
separately, and the v1-to-v2 change must not be interpreted causally because several components changed.

Human inter-reviewer agreement and human Cohen's kappa are not estimable: no independent human labels
have been entered. AI technical adjudication must never be reported as human review.

## Endpoint Plan

Primary endpoint for a future frozen test run:

- MIDI-B required-action accuracy for each prespecified workflow on the untouched test collection.

Secondary endpoints:

- action, category, modality, and SOP-class performance;
- residual identifiers and false information destruction;
- unreadable, missing, partial, or quarantined outputs;
- IOD-aware PS3.15 and DICOM validity outcomes;
- corpus-level linkage and reference failures;
- automated-human agreement and review workload; and
- runtime, throughput, peak memory, and failure recovery.

## Methods Outline

1. Freeze protocol, endpoints, tools, configurations, analysis code, and review rubric.
2. Use the validation collection only for integration verification and prespecified fixes.
3. Execute each frozen workflow once on the untouched test collection.
4. Run the unmodified official validator and any documented compatibility analysis separately.
5. Run path-aware internal, IOD, DICOM-validity, and corpus-level checks.
6. Draw a prespecified stratified sample for blinded dual human review and adjudication.
7. Report confusion matrices, Wilson intervals, paired tests, multiplicity handling, and clustered sensitivity analyses.
8. Release code, schemas, non-PHI manifests, redacted configurations, checksums, SBOMs, and provenance.

## Human Review Gate

The current 280-row assisted worklist has 180 rows marked for independent human signoff, plus four
residual token-policy rows. Human fields are blank. Before making human-validated semantic or visual
claims, obtain paired independent labels, resolve disagreements under the frozen rubric, and then
calculate inter-reviewer agreement and Cohen's kappa.

## Claims To Avoid

- Do not call the software a PS3.15, HIPAA, GDPR, or clinical compliance certificate.
- Do not claim zero residual risk from zero automated findings.
- Do not present the compatibility-patched validator as the unmodified official validator.
- Do not describe AI-assisted technical review as independent human review.
- Do not report human agreement when paired human labels do not exist.
- Do not call the validation-split baseline the frozen primary test result.
- Do not attribute the bundled v1-to-v2 change to one component.
- Do not generalize beyond evaluated modalities, SOP classes, manufacturers, transfer syntaxes, and configurations.

## Publication Artifact

The sanitized private manuscript package contains:

```text
manuscript-results-v2-final/
|-- MANUSCRIPT_RESULTS.md
|-- publication_statistics.json
|-- evaluator_confusion_matrix.csv
|-- action_disagreement_adjudication.csv
|-- targeted_adjudication_summary.csv
|-- residual_pass_fail_review_summary.csv
|-- reviewer_agreement_status.csv
`-- SHA256SUMS.txt
```

The package excludes raw values, patient identifiers, DICOM paths, action IDs, and machine-specific
paths. Human-reviewed claims remain gated even though the technical package is complete.

## Next Publication Gates

1. Complete paired independent human review and adjudication.
2. Freeze the primary test protocol and all workflow binaries/configurations.
3. Run the untouched MIDI-B test split and unmodified official comparator.
4. Generate confidence intervals and prespecified paired/sensitivity analyses.
5. Publish only aggregate non-PHI artifacts and verified checksum manifests.

---

DICOM is the registered trademark of the National Electrical Manufacturers Association for its
standards publications relating to digital communications of medical information. See
[Legal notices](LEGAL_NOTICES.md).
