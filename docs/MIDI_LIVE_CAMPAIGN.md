# Complete MIDI-B live-tool campaign

The campaign runner applies one or more configured de-identification workflows to a complete imported MIDI-B corpus, evaluates the outputs, and records reproducibility metadata.

This is an opt-in real-data workflow. The public GitHub demo should use the synthetic demonstration in [Demo](DEMO.md). Do not commit MIDI-B DICOM objects, answer-key databases, reviewer identity mappings, or unredacted validation logs.

## Dataset preparation

Download the public MIDI-B resources independently from TCIA after the project owner accepts the applicable terms. The project does not redistribute the data. Keep the corpus and answer-key database outside the repository, then import the answer key and source objects:

```bash
dicom-privacy-midi import \
  /data/midi/answer-key.sqlite \
  /data/midi/synthetic-validation \
  workspaces/midi-import \
  --patient-mapping /data/midi/patient-mapping.csv \
  --uid-mapping /data/midi/uid-mapping.csv \
  --overwrite
```

## Preflight and migrated corpora

Before a long run, verify that the imported answer-key bundle and source corpus are available:

```bash
dicom-privacy-campaign preflight workspaces/midi-import
```

The import manifest records the source location used at import time. After moving the corpus to another machine or mount point, supply a non-destructive override:

```bash
dicom-privacy-campaign preflight workspaces/midi-import \
  --source-root /new/location/synthetic-validation
```

Use the same `--source-root` option with `run`, `run-tool`, and `finalize-tool`. The manifest is not rewritten.

## Resumable sharded execution

Large runs can be split deterministically across workers. Each source relative path is assigned to exactly one hash-based shard, independent of directory traversal order:

```bash
# Worker 0
dicom-privacy-campaign run-tool workspaces/midi-import workspaces/midi-live \
  --tool orthanc --config configs/orthanc.example.json \
  --source-root /data/midi/synthetic-validation \
  --shard-index 0 --shard-count 4 --no-evaluate

# Repeat with shard indices 1, 2, and 3 against the same shared workspace.
```

Completed destination files are validated and skipped on restart. Append-only per-shard checkpoint logs are written under `workspace/checkpoints/`. A shard-specific `--overwrite` only replaces files assigned to that shard; it does not erase outputs from other shards.

After every shard has completed, run final evaluation once:

```bash
dicom-privacy-campaign finalize-tool workspaces/midi-import workspaces/midi-live \
  --tool orthanc --source-root /data/midi/synthetic-validation \
  --official-validator-command configs/official-midi-validator-command.example.json \
  --official-validator-timeout-seconds 3600
```

Finalization refuses to proceed when the assembled output contains fewer readable DICOM instances than the source corpus.

## Run one tool

```bash
dicom-privacy-campaign run-tool \
  workspaces/midi-import \
  workspaces/midi-live \
  --tool orthanc \
  --config configs/orthanc.example.json \
  --official-validator-command configs/official-midi-validator-command.example.json \
  --overwrite
```

## Run a complete comparison

```bash
dicom-privacy-campaign run \
  workspaces/midi-import \
  workspaces/midi-live \
  configs/midi-live-campaign.example.json \
  --overwrite
```

Each tool run records:

- application version;
- configuration SHA-256;
- imported MIDI manifest SHA-256;
- operating system, Python version, and architecture;
- adapter probe result;
- source, processed, and failed instance counts;
- runtime;
- internal MIDI action-level evaluation summary;
- official-validator command return code and output tail, when configured; and
- per-case failures using hashed case identifiers.

## Publication evidence and review sampling

After final evaluation, create a deterministic action-stratified review sample:

```bash
dicom-privacy-campaign review-sample \
  workspaces/midi-live/evaluations/orthanc/evaluation.json \
  workspaces/midi-live/reports/orthanc-review-sample.json \
  --failures-per-stratum 25 --controls-per-stratum 10 --seed 20260620
```

Normalize the official validator SQLite output into the same action-id namespace as
the internal evaluator, then calculate evaluator parity:

```bash
dicom-privacy-campaign normalize-official-midi \
  workspaces/midi-live/official/orthanc/validation_results.db \
  private/MIDI-B-Answer-Key-Validation.db \
  workspaces/midi-live/imported/uid_mapping.csv \
  workspaces/midi-live/official/orthanc-normalized.csv \
  --unmatched-output workspaces/midi-live/official/orthanc-unmatched.csv

dicom-privacy-campaign parity-stream \
  workspaces/midi-live/evaluations/orthanc/midi_results.csv \
  workspaces/midi-live/official/orthanc-normalized.csv \
  workspaces/midi-live/reports/orthanc-parity.json
```

For smaller JSON-only experiments, the legacy in-memory comparator is still available:

```bash
dicom-privacy-campaign parity \
  workspaces/midi-live/evaluations/orthanc/evaluation.json \
  workspaces/midi-live/official/orthanc-normalized.json \
  workspaces/midi-live/reports/orthanc-parity.json
```

Assemble a redacted evidence directory and checksum manifest:

```bash
dicom-privacy-campaign evidence-package \
  workspaces/midi-live validation/live/midi-test-orthanc \
  --campaign-id midi-test-orthanc --overwrite
```

The evidence builder copies JSON records only, redacts known operational path fields, and writes `SHA256SUMS.txt`. Review every exported file before public release because free-text fields may still contain sensitive content entered by operators or reviewers.

## Manuscript controls

A defensible comparison should include:

1. no-op negative control;
2. transparent internal baseline;
3. Orthanc with a frozen configuration;
4. RSNA DICOM Anonymizer with a frozen project model;
5. RSNA CTP with a frozen pipeline configuration;
6. official MIDI validation-script results;
7. internal-versus-official evaluator parity checks;
8. DICOM validity and corpus-consistency checks;
9. blinded pixel/metadata review of failures and a negative-control sample; and
10. exact software versions or container image digests.

## Execution status

The repository contains the complete campaign orchestration and synthetic integration tests. A full official collection run is environment-dependent and must not be claimed until the TCIA data and live tool installations have actually been processed. Record completed external runs in `validation/live/` using the included template.

For setup details and suggested local directory layout, see [Real data setup](REAL_DATA_SETUP.md).

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).


## Seal and verify campaign evidence

After building the redacted evidence directory, verify and archive it deterministically:

```bash
dicom-privacy-campaign verify-evidence evidence/
dicom-privacy-campaign archive-evidence evidence/ campaign-evidence.tar.gz --source-date-epoch 0
dicom-privacy-campaign verify-evidence campaign-evidence.tar.gz
```

Verification rejects checksum mismatches, missing files, unexpected files, malformed/duplicate manifest entries, symbolic links, unsafe or duplicate archive members, and configured member/uncompressed-size limits. Evidence directories and archives must not overlap. Archive metadata is normalized so identical evidence directories and source-date epochs produce byte-identical archives.
