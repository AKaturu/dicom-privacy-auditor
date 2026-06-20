# Corpus-level consistency evaluation

Single-file evaluation cannot establish that pseudonyms, UIDs, references, and date shifts remain coherent across a collection. The corpus evaluator compares paired source and candidate trees and reports collection-wide failures.

## Run

```bash
dicom-privacy-corpus evaluate \
  /data/source \
  /data/candidate \
  --json reports/corpus.json \
  --csv reports/corpus-findings.csv
```

By default, files are paired by relative path. Use a mapping CSV when a pipeline changes paths:

```csv
source_path,candidate_path
study-a/source-1.dcm,output/anon-0001.dcm
```

```bash
dicom-privacy-corpus evaluate source candidate \
  --mapping-csv mapping.csv \
  --json reports/corpus.json
```

## Checks

- one source UID mapping to multiple candidate UIDs;
- multiple source UIDs colliding into one candidate UID;
- one patient mapping to multiple pseudonyms;
- multiple patients colliding into one pseudonym;
- retained patient identifiers;
- inconsistent date-shift offsets within one source patient;
- referenced UIDs that do not follow identity-UID mappings;
- File Meta SOP Class/Instance UID disagreement; and
- unmatched source or candidate objects.

Identifier values and root paths are hashed by default. `--disclose-paths` should only be used in a controlled local investigation.

## Interpretation

A zero-finding report means that the implemented consistency checks did not detect a problem in the paired corpus. It does not prove that:

- every identifying field was removed;
- pseudonyms are cryptographically secure;
- all conditional DICOM references are valid;
- every non-DICOM sidecar file was handled; or
- dates satisfy a specific legal de-identification policy.

Use the corpus report together with PS3.15/IOD evaluation, a DICOM validator, pixel review, and the MIDI-B action evaluator.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
