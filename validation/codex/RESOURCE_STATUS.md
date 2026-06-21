# Resource Status

| Resource | Status | Version/ID | SHA-256 or digest | Authoritative source | License/terms | Notes |
|---|---|---|---|---|---|---|
| Original v0.7.1 handoff ZIP | verified | v0.7.1 handoff | 1af0ccdf338527691daa97f372bebcaa07e1dd6223f47392ae962fcab354654a | user-supplied archive | project release terms | Verified before extraction. |
| Handoff file manifest | verified | HANDOFF_SHA256SUMS.txt | n/a | archive manifest | n/a | Every listed file matched. |
| Release artifact manifest | verified | artifacts/SHA256SUMS-v0.7.1.txt | n/a | archive manifest | n/a | Source ZIP, wheel, sdist, and completion report matched. |
| Local release gate | complete | v0.7.2 patched tree | see `validation/codex/baseline/local-release-gate.json` | local execution | n/a | Passed after environment correction and portability fixes. |
| MIDI-B validation collection | partially acquired | `.tcia` manifests dated 2025-05-02 | see `validation/codex/external/MIDI_B_PUBLIC_RESOURCE_INVENTORY.json` | TCIA MIDI-B collection page | TCIA terms required | Public synthetic validation/test manifests and mapping CSVs were downloaded to `D:/CodexExternal/MIDI-B`; the DICOM corpus itself is not downloaded. |
| MIDI-B frozen test collection | missing | | | TCIA/Synapse challenge resources | terms required | Not supplied; final campaign blocked. |
| MIDI-B answer key and mapping files | partial | Faspex packages 1042/1043; public mapping CSVs acquired | see `validation/codex/external/MIDI_B_PUBLIC_RESOURCE_INVENTORY.json` | TCIA/Synapse challenge resources | terms required | Public mapping CSVs are acquired; the SQLite answer-key databases still require an authenticated Faspex bearer-token transfer. |
| Official MIDI-B validator | available, not executed | CBIIT commit `5273eb7e4a560c68b3da2bb22bb31a58ca689e17` | wrapper fingerprint in `validation/codex/external-preflight-real-public.json` | CBIIT `MIDI_validation_script` | Apache-2.0 | Requirements installed in a Python 3.11 venv and imports smoke-tested; official run is blocked until corpus and answer DB exist. |
| Orthanc | executed | `orthancteam/orthanc:26.6.0` / Orthanc `1.12.11` | digest in `validation/codex/external/REAL_EXTERNAL_SOURCES_RECORD.json` | Orthanc Docker documentation / Docker Hub | Orthanc/image license review required | HTTP, DIMSE, and DICOMweb probes passed while the local container was running; container was stopped after evidence capture. |
| RSNA DICOM Anonymizer | executed / installed | DAT legacy tool and `rsna-anonymizer` 18.0.7 | hashes and wrapper fingerprints in `validation/codex/external/REAL_EXTERNAL_SOURCES_RECORD.json` | RSNA imaging research tools / RSNA GitHub/PyPI | license review required | Legacy DAT benchmark ran on synthetic data; modern Python RSNA anonymizer installed under Python 3.12 and `--help` smoke-tested. |
| RSNA CTP | acquired, not pipeline-executed | CTP installer/extracted Runner.jar | hashes in `validation/codex/external/REAL_EXTERNAL_SOURCES_RECORD.json` | RSNA MIRC CTP resources | RSNA terms/license review required | Wrapper is discoverable for preflight; `Runner.jar -help` still throws `NullPointerException`, and no directory anonymization pipeline was executed. |
| Additional independent workflow | missing | | | to be supplied | to be supplied | No additional approved workflow supplied. |
| Reviewer A | missing | coded only | n/a | project owner/institution | n/a | Real independent reviewer not supplied. |
| Reviewer B | missing | coded only | n/a | project owner/institution | n/a | Real independent reviewer not supplied. |
| Adjudicator | missing | coded only | n/a | project owner/institution | n/a | Qualified adjudicator not supplied. |
| Institutional authorization | not performed | | n/a | project owner/institution | authorization required | No written authorization or endpoint credentials supplied. |
| Windows x64 native runner | partially local only | local Windows 11 Python checks | n/a | local machine | n/a | Local Python release gate passed; GitHub Actions native runner/provenance not supplied. |
| macOS arm64 runner | missing | | n/a | GitHub Actions or owner runner | n/a | Not supplied. |
| macOS x64 runner | missing | | n/a | GitHub Actions or owner runner | n/a | Not supplied. |
| Authenticode credentials | missing | secret | n/a | owner-controlled secret store | credential terms | Not supplied; signing not claimed. |
| Apple signing/notary credentials | missing | secret | n/a | owner-controlled secret store | credential terms | Not supplied; signing/notarization not claimed. |
