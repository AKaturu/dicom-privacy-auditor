# Pre-specified Validation Study Protocol

## Working title

**Standards-, benchmark-, corpus-, and human-review evaluation of DICOM de-identification workflows**

## Study objective

Compare selected DICOM de-identification workflows using four complementary layers:

1. seeded synthetic identifiers;
2. the public MIDI-B answer key and official validator;
3. IOD-aware PS3.15 and corpus-level integrity evaluation; and
4. blinded human review of pixels and metadata.

The goal is to measure both privacy performance and preservation of usable, internally consistent DICOM objects. The study does not treat any automated score as proof that a dataset is safe to release.

## Primary hypotheses

1. Identifier-removal performance differs by location, action type, modality, and workflow.
2. Metadata-oriented workflows perform worse on filenames, pixels, recognizable visual features, and embedded content than on common top-level attributes.
3. File-level evaluation misses UID, pseudonym, date-shift, and cross-object reference failures detectable only at corpus level.
4. Automated review and human adjudication disagree in a nonzero proportion of cases, supporting a human-in-the-loop release process.
5. IOD context changes the expected disposition of some attributes compared with a table-only PS3.15 interpretation.

## Design

Repeated-measures technical validation. Every workflow receives the same frozen source corpus. Tool versions, configurations, container digests or executable hashes, adapter behavior, filename policy, and all evaluator versions are frozen before final analysis.

### Phases

- **Phase A:** seeded ten-stratum synthetic benchmark and clean controls;
- **Phase B:** full MIDI-B validation collection for integration and threshold development;
- **Phase C:** frozen MIDI-B test collection for final external performance;
- **Phase D:** IOD-aware PS3.15, DICOM validity, and corpus-integrity evaluation;
- **Phase E:** stratified blinded dual review with adjudication;
- **Phase F:** optional institutionally approved clinical-export validation.

## Workflows

At minimum:

- no-op negative control;
- internal transparent baseline/positive technical control;
- Orthanc;
- RSNA DICOM Anonymizer;
- RSNA CTP; and
- at least one independent institutional or open-source workflow.

The benchmark-aware internal control must not be presented as a competitive or deployable clinical system.

## Experimental units

- **Primary:** required MIDI-B action or seeded identifier instance;
- **Secondary:** DICOM instance;
- **Cluster:** patient, study, series, SOP class, modality, manufacturer, or tool run;
- **Human review:** unique case/scope/target/frame/region decision.

## Outcomes

### Primary

Required-action accuracy for each workflow:

`correctly completed required actions / scored required actions`

The seeded benchmark additionally reports identifier-removal rate.

### Secondary

- residual-identifier rate;
- false removal or destruction of required information;
- unresolved and processing-error rates;
- output readability and transfer-syntax preservation;
- IOD-aware PS3.15 pass/review/fail counts;
- UID one-to-many mappings and collisions;
- broken reference mappings;
- pseudonym one-to-many mappings, collisions, and retained identifiers;
- inconsistent within-patient date shifts;
- File Meta and main-dataset UID disagreement;
- study-level completion, quarantine, and upload status;
- runtime, throughput, and failure recovery;
- human-review confirmation rate, review time, exact agreement, and Cohen's kappa;
- performance by action, category, modality, SOP class, manufacturer, and workflow.

## Ground truth

- Seeded phase: frozen injection manifest and clean-control manifest.
- MIDI-B phase: supplied SQLite answer key, patient mapping, UID mapping, collection version, and official validation software.
- Human review: independent decisions by two trained reviewers with adjudication by an imaging-informatics expert or radiologist.
- IOD context: user-local checksum-recorded registry generated from separately obtained source material; no standards tables are redistributed by the project.

## Human-review sampling

Use a prespecified stratified sample containing:

- every automated residual or processing error;
- all pixel/recognizable-feature actions;
- all IOD/corpus failures;
- a random sample of automated passes from every tool/action stratum; and
- clean or legitimate-text controls for estimating false-positive burden.

Reviewers remain blinded to tool identity and each other's decisions until adjudication. The review database and export hashes are archived with access controls.

## Statistical analysis

- Wilson 95% confidence intervals for proportions.
- Exact McNemar tests for paired workflow outcomes.
- Holm correction for prespecified multiple pairwise comparisons.
- Mixed-effects logistic regression when clustering materially affects inference.
- Exact agreement and Cohen's kappa for dual review; report prevalence and category-specific agreement because kappa is prevalence-sensitive.
- Conservative treatment of missing, unreadable, incomplete, or unresolvable outputs as failures in the primary analysis; sensitivity analyses may report them separately.
- Runtime summarized with median, interquartile range, throughput, and paired nonparametric comparisons where appropriate.
- Internal evaluator results must be compared with the official MIDI-B validator before final analysis.

## Reproducibility requirements

- frozen source collection identifiers and file checksums;
- imported MIDI manifest and answer-key/mapping hashes;
- application version and commit SHA;
- tool executable/container digest and configuration hash;
- operating system, CPU, memory, storage, and relevant library versions;
- machine-readable run, quarantine, corpus, IOD, review, and official-validator outputs;
- SHA-256 checksum manifest, SBOM, and build attestation for released binaries;
- no real PHI in the public repository or CI artifacts;
- no redistributed DICOM standards document or complete extracted standards tables.

## Safety and governance

The synthetic and MIDI-B phases use public/synthetic resources. Any clinical phase requires written institutional determination, data-use authorization, privacy/security review, minimum-necessary access, controlled review workstations, release-risk assessment, and an incident-response plan. DICOMweb and adapter endpoints must be dedicated or explicitly approved; automated cleanup must never target a clinical archive.

## Pre-publication completion criteria

A final comparative manuscript requires:

1. full validation and test collection execution;
2. live frozen external-tool installations;
3. official-validator parity analysis;
4. corpus and IOD-aware reports;
5. blinded dual review and adjudication;
6. complete accounting of failures, quarantines, and deviations; and
7. independently verifiable artifacts and checksums.

## Planned figures

1. End-to-end benchmark, tool, corpus, and review flow
2. Required-action accuracy by workflow and action type
3. Residual/error heat map by modality and SOP class
4. Corpus-integrity failure network or taxonomy
5. Automated versus human-review agreement
6. Runtime and throughput

## Planned tables

1. Dataset and action composition
2. Frozen tool versions and configurations
3. Overall and action-specific performance
4. IOD/corpus validity and preservation outcomes
5. Human adjudication and interrater agreement
6. Processing failures, quarantines, and protocol deviations
