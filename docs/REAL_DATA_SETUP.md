# Real Data Setup

The public repository is synthetic-first. Demos, tests, examples, screenshots, and generated demo media should use synthetic DICOM objects created by this project. Real MIDI-B data, institutional exports, answer keys, reviewer databases, and endpoint credentials must stay outside Git and outside public release artifacts.

Use real data only for governed validation, never for the default GitHub demo path.

## Recommended Layout

Keep real inputs in a local directory that is not inside the repository:

```text
/secure/dicom-privacy-data/
  midi-b/
    manifests/
    mappings/
    answer-keys/
    source-dicom/
    candidate-output/
  tools/
    midi-validation-script/
    rsna-anonymizer/
    rsna-ctp/
```

On Windows, an external drive path such as `D:/CodexExternal/MIDI-B` is fine. Do not move the DICOM corpus or answer-key database under the project tree.

## Synthetic Demo Path

For demos and GitHub screenshots/videos, use:

```bash
dicom-privacy-demo demo-release --overwrite
```

or:

```bash
python scripts/run_demo_benchmark.py --workspace examples/demo_workspace --overwrite
```

These commands create synthetic DICOM objects and synthetic identifiers. They do not require MIDI-B, TCIA, Synapse, reviewer credentials, institutional endpoints, or signing credentials.

## MIDI-B Real Data Path

1. Review and accept the applicable TCIA/Synapse/NCI terms under the project owner's account.
2. Download the official `.tcia` manifests and mapping CSVs from the TCIA MIDI-B collection page.
3. Download the answer-key package through the TCIA/Faspex authenticated transfer flow.
4. Download the DICOM corpus from the `.tcia` manifests with the TCIA/NBIA Data Retriever workflow or another approved TCIA workflow.
5. Hash every downloaded manifest, mapping file, answer-key database, and corpus inventory before running validation.
6. Import the corpus from its external location:

```bash
dicom-privacy-midi inspect /secure/dicom-privacy-data/midi-b/answer-keys/answer_key.sqlite

dicom-privacy-midi import \
  /secure/dicom-privacy-data/midi-b/answer-keys/answer_key.sqlite \
  /secure/dicom-privacy-data/midi-b/source-dicom \
  workspaces/midi-import \
  --patient-mapping /secure/dicom-privacy-data/midi-b/mappings/patient_mapping.csv \
  --uid-mapping /secure/dicom-privacy-data/midi-b/mappings/uid_mapping.csv \
  --dataset-name MIDI-B-Validation \
  --overwrite
```

The import workspace stores metadata and provenance, not a public copy of the source corpus.

## External Preflight

Create a local config from `configs/external-validation.example.json`, then point it to local resources:

```json
{
  "midi_b_corpus": "/secure/dicom-privacy-data/midi-b/source-dicom",
  "midi_b_answer_key": "/secure/dicom-privacy-data/midi-b/answer-keys/answer_key.sqlite",
  "official_validator_command": "validation/codex/external/midi-validator.cmd",
  "rsna_anonymizer_command": "validation/codex/external/rsna/run-rsna-anonymizer.cmd",
  "rsna_ctp_command": "validation/codex/external/rsna/run-ctp.cmd",
  "orthanc_http_url": "http://127.0.0.1:8042/system",
  "orthanc_dimse_host": "127.0.0.1",
  "orthanc_dimse_port": 4242,
  "dicomweb_url": "http://127.0.0.1:8042/dicom-web/studies?limit=1",
  "reviewers": ["reviewer-a", "reviewer-b"],
  "fingerprint_mode": "content"
}
```

Run:

```bash
dicom-privacy-external local-external-validation.json \
  --output validation/live/external-preflight-private.json \
  --write-lock validation/live/external-resources.lock.json
```

Use `--redact-paths` for public summaries.

## What May Be Committed

- Synthetic demo outputs.
- Redacted evidence summaries.
- Hash manifests.
- Resource locks that do not expose secrets or raw paths.
- Configuration examples with placeholder paths.

## What Must Not Be Committed

- DICOM objects from TCIA, Synapse, or institutional systems.
- MIDI-B answer-key databases unless the project owner has approved redistribution. The default is no.
- Reviewer identity mappings or adjudication databases with real reviewer identities.
- Endpoint tokens, credentials, signing keys, private certificates, or notary credentials.
- Reversible pseudonym maps.
- Unredacted logs containing local paths, PHI, UIDs, or operational secrets.

## Claim Boundary

Synthetic demonstrations are useful for showing the application workflow and UI. They are not MIDI-B validation, clinical safety evidence, regulatory clearance, or human review. Real-data results should be claimed only after the real corpus, answer key, tool versions, reviewer process, and resource fingerprints are archived in a governed validation record under `validation/live/`.
