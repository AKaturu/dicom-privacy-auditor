# MIDI-B importer and evaluator

## Purpose

The MIDI-B module normalizes the public Medical Imaging De-Identification Benchmark answer key and evaluates a candidate de-identification output without copying the source image collection. It is designed for the public SQLite answer keys and patient/UID mapping CSV files distributed with the MIDI-B validation and test collections.

The public GitHub project does not include MIDI-B DICOM objects or answer-key databases. Use the built-in synthetic benchmark for demonstrations and reserve MIDI-B for governed local validation. See [Real data setup](REAL_DATA_SETUP.md) before downloading or importing real resources.

## Supported answer-key actions

The importer recognizes all ten published action labels:

1. `date shifted`
2. `patid consistent`
3. `pixels hidden`
4. `pixels retained`
5. `tag retained`
6. `text notnull`
7. `text removed`
8. `text retained`
9. `uid changed`
10. `uid consistent`

## Inspect before importing

```bash
dicom-privacy-midi inspect /data/midi/answer_key.sqlite
```

This prints every SQLite table, row count, column names, detected action column, and recognized action values. Review this output whenever a new MIDI-B release is used.

## Import

```bash
dicom-privacy-midi import \
  /data/midi/answer_key.sqlite \
  /data/midi/source-dicom \
  workspaces/midi-import \
  --patient-mapping /data/midi/patient_mapping.csv \
  --uid-mapping /data/midi/uid_mapping.csv \
  --dataset-name MIDI-B-Validation \
  --overwrite
```

The importer:

- hashes the answer key for provenance;
- indexes source DICOM objects by SOP Instance UID and Patient ID;
- normalizes actions to `actions.jsonl`;
- copies mapping CSVs into the imported workspace;
- reports unresolved source paths without copying the source dataset.

For an unfamiliar SQLite schema, provide an explicit field-to-column map:

```json
{
  "action": "RequiredAction",
  "sop_instance_uid": "SourceSOPInstanceUID",
  "patient_id": "OriginalPatientID",
  "tag": "DicomTag",
  "value": "ExpectedText",
  "relative_path": "SourcePath",
  "coordinates": "BoundingBox"
}
```

```bash
dicom-privacy-midi import ... --column-map midi-columns.json
```

## Evaluate

```bash
dicom-privacy-midi evaluate \
  workspaces/midi-import \
  /data/midi/candidate-output \
  workspaces/midi-evaluation
```

Outputs:

```text
midi_evaluation.json
midi_results.csv
MIDI_REPORT.md
```

The report includes overall score plus results by action and category. Unresolved actions and read/decoding errors are separated from scored pass/fail actions.

## Matching logic

Candidate objects are resolved in this order:

1. mapped SOP Instance UID;
2. unchanged SOP Instance UID;
3. mapped Patient ID when exactly one candidate object matches;
4. source-relative path.

Use dedicated candidate directories and preserve the official mapping files to avoid ambiguous matching.

## Evaluation semantics and limitations

- `date shifted` and `uid changed` require a non-empty changed value.
- `patid consistent` and `uid consistent` require the supplied mapping CSV.
- text actions use literal substring tests against the target attribute.
- `pixels hidden` requires a usable bounding box and verifies that the target region changed.
- `pixels retained` currently requires exact decoded-pixel equality.

Exact pixel equality is intentionally conservative. It can mark lossless-equivalent transformations as failures if decoded arrays differ, and it is not a perceptual-similarity metric. Literal text checks do not determine whether surrounding content remains clinically useful or semantically identifying.

## Validation status

The importer/evaluator is covered by a complete ten-action SQLite fixture in the automated test suite. The full public MIDI-B collections are not redistributed with this repository and are not part of the synthetic demo. A publication analysis should archive the exact TCIA collection version, answer-key checksum, mapping checksums, tool configuration, and evaluation outputs.

Public collection page:

```text
https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/
```
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
