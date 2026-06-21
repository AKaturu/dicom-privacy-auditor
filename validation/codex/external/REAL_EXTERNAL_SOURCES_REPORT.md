# Real External Sources Evidence Addendum

Generated: 2026-06-21T03:25:10Z

## Status

Real public external sources were used where they were reachable without private credentials. This addendum does not convert the release to full external validation. The real-source preflight is still `blocked`, but it improved from 4 of 10 to 7 of 10 required checks ready after installing and wiring real external tooling.

## Real sources used

- TCIA MIDI-B collection: https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/
- MIDI resources paper: https://arxiv.org/abs/2508.01889
- Synapse MIDI-B challenge: https://www.synapse.org/Synapse:syn53065760
- Orthanc Docker documentation: https://orthanc.uclouvain.be/book/users/docker.html
- Docker Hub orthancteam/orthanc: https://hub.docker.com/r/orthancteam/orthanc
- RSNA DicomAnonymizerTool wiki: https://mircwiki.rsna.org/index.php?title=The_DicomAnonymizerTool
- RSNA legacy downloads: https://github.com/RSNA/mirc.rsna.org
- RSNA Anonymizer PyPI: https://pypi.org/project/rsna-anonymizer/
- RSNA Anonymizer source metadata: https://github.com/RSNA/anonymizer/blob/master/pyproject.toml
- NBIA Toolkit documentation: https://nbia-toolkit.readthedocs.io/en/latest/
- TCIA/NBIA Data Retriever CLI documentation: https://wiki.cancerimagingarchive.net/display/NBIA/NBIA+Data+Retriever+Command-Line+Interface+Guide
- CBIIT MIDI validation script: https://github.com/CBIIT/MIDI_validation_script
- IBM Aspera Faspex package download API documentation: https://www.ibm.com/docs/en/aspera-faspex/5.0?topic=packages-downloading-package-connect

## Executed real-source workflows

### Orthanc

- Image: `orthancteam/orthanc:26.6.0`
- Digest: `orthancteam/orthanc@sha256:510ef4ce24699104244b00d2b93350a801fc2f1c6b0bfc6a1f15e546bff2d1f4`
- Orthanc version from `/system`: `1.12.11`
- Probes: HTTP `/system` 200, DIMSE TCP 4242 connected, DICOMweb studies endpoint 200.
- Synthetic benchmark: 12 cases, 12 readable outputs, 12 basic-valid outputs, removal rate 0.900, residual injections 1.

### RSNA DicomAnonymizerTool

- Source: RSNA legacy downloads plus RSNA DAT wiki command documentation.
- Downloaded installer hashes are recorded in `REAL_EXTERNAL_SOURCES_RECORD.json`.
- Synthetic benchmark: 12 cases, 12 readable outputs, 12 basic-valid outputs, removal rate 0.800, residual injections 2.
- CTP note: the acquired CTP installation is discoverable through `validation/codex/external/rsna/run-ctp.cmd`, so the preflight command-availability check is ready. `Runner.jar -help` still throws `NullPointerException`; no CTP directory anonymization pipeline has been executed or claimed.

### MIDI-B Public Resource Acquisition

- TCIA public `.tcia` manifests and public patient/UID mapping CSVs were downloaded to `D:/CodexExternal/MIDI-B`.
- Hashes and byte counts are recorded in `MIDI_B_PUBLIC_RESOURCE_INVENTORY.json`.
- The full DICOM corpus was not downloaded from the manifests during this run.
- TCIA/Faspex answer-key package IDs were identified, but the answer-key databases were not downloaded because the Faspex API requires an authenticated bearer-token transfer flow.

### CBIIT MIDI Validator

- Source cloned from `https://github.com/CBIIT/MIDI_validation_script`.
- Local commit: `5273eb7e4a560c68b3da2bb22bb31a58ca689e17`.
- Python 3.11 virtual environment installed the repository requirements, including EasyOCR/Torch and NLTK dependencies.
- Smoke test imported `run_validation`, `run_reports`, and `run_dciodvfy`; no official MIDI validation run was performed because the DICOM corpus and answer-key database are still absent.

### Modern RSNA Anonymizer

- Python 3.12.10 was installed locally.
- `rsna-anonymizer` 18.0.7 was installed into `D:/CodexExternal/venvs/rsna-anonymizer-312`.
- `rsna-anonymizer --help` succeeded and is wired through `validation/codex/external/rsna/run-rsna-anonymizer.cmd`.

### IBM Aspera

- IBM Aspera Desktop was installed with `ascp` available at `C:/Program Files/IBM Aspera/transferd/bin/ascp.exe`.
- `ascp -A` reported version `4.4.7.2245`.
- This removes the local transfer-client blocker only. The Faspex package still needs an authenticated bearer token before a transfer spec can be requested.

## External preflight

Ready checks: official_validator, rsna_anonymizer, rsna_ctp, orthanc_http, orthanc_dimse, dicomweb, credentials.

Missing required checks: midi_b_corpus, midi_b_answer_key, blinded_reviewers.

## Blockers that remain

- MIDI-B DICOM corpus and answer-key database are not present locally. Public manifests and mapping CSVs are acquired and hashed, but they are not substitutes for the actual corpus/answer DB.
- Synapse challenge access/scoring is closed or governed and must use authorized project-owner access.
- RSNA CTP needs a working pipeline configuration before it can be counted as executed, even though the command wrapper is now discoverable.
- Independent blinded reviewers, adjudicator, institutional authorization, native runner provenance, and signing/notary credentials were not supplied.

## Container lifecycle

The Orthanc container was stopped and removed after evidence collection. The preflight JSON records endpoint readiness while it was running.

## Claim boundary

This is real external-source acquisition and execution evidence on synthetic data. It is not official MIDI-B validation, not clinical safety evidence, not regulatory clearance, and not human reviewer sign-off.
