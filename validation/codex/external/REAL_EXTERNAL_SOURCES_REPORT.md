# Real External Sources Evidence Addendum

Generated: 2026-06-20T23:42:35Z

## Status

Real public external sources were used where they were reachable without private credentials. This addendum does not convert the release to full external validation. The real-source preflight is still `blocked` with 4 of 10 required checks ready.

## Real sources used

- TCIA MIDI-B collection: https://www.cancerimagingarchive.net/collection/midi-b-test-midi-b-validation/
- MIDI resources paper: https://arxiv.org/abs/2508.01889
- Synapse MIDI-B challenge: https://www.synapse.org/Synapse:syn53065760
- Orthanc Docker documentation: https://orthanc.uclouvain.be/book/users/docker.html
- Docker Hub orthancteam/orthanc: https://hub.docker.com/r/orthancteam/orthanc
- RSNA DicomAnonymizerTool wiki: https://mircwiki.rsna.org/index.php?title=The_DicomAnonymizerTool
- RSNA legacy downloads: https://github.com/RSNA/mirc.rsna.org
- RSNA Anonymizer PyPI: https://pypi.org/project/rsna-anonymizer/
- NBIA Toolkit documentation: https://nbia-toolkit.readthedocs.io/en/latest/

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
- CTP note: Runner.jar still throws `NullPointerException` on `-help`; CTP was not counted as ready.

## External preflight

Ready checks: orthanc_http, orthanc_dimse, dicomweb, credentials.

Missing required checks: midi_b_corpus, midi_b_answer_key, official_validator, rsna_anonymizer, rsna_ctp, blinded_reviewers.

## Blockers that remain

- MIDI-B data, answer keys, mappings, and official validator were not supplied. Local free space after downloads was 3,699,666,944 bytes, below the observed 7.63 GB validation download alone.
- Synapse challenge access/scoring is closed or governed and must use authorized project-owner access.
- Modern `rsna-anonymizer` was not installed because PyPI metadata requires Python >=3.12,<3.13 and this host exposes Python 3.11.
- RSNA CTP needs a working pipeline configuration before it can be counted as executed.
- Independent blinded reviewers, adjudicator, institutional authorization, native runner provenance, and signing/notary credentials were not supplied.

## Container lifecycle

The Orthanc container was stopped and removed after evidence collection. The preflight JSON records endpoint readiness while it was running.

## Claim boundary

This is real external-source acquisition and execution evidence on synthetic data. It is not official MIDI-B validation, not clinical safety evidence, not regulatory clearance, and not human reviewer sign-off.
