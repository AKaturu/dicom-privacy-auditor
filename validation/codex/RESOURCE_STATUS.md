# Resource Status

| Resource | Status | Version/ID | SHA-256 or digest | Authoritative source | License/terms | Notes |
|---|---|---|---|---|---|---|
| Original v0.7.1 handoff ZIP | verified | v0.7.1 handoff | 1af0ccdf338527691daa97f372bebcaa07e1dd6223f47392ae962fcab354654a | user-supplied archive | project release terms | Verified before extraction. |
| Handoff file manifest | verified | HANDOFF_SHA256SUMS.txt | n/a | archive manifest | n/a | Every listed file matched. |
| Release artifact manifest | verified | artifacts/SHA256SUMS-v0.7.1.txt | n/a | archive manifest | n/a | Source ZIP, wheel, sdist, and completion report matched. |
| Local release gate | complete | v0.7.2 patched tree | see `validation/codex/baseline/local-release-gate.json` | local execution | n/a | Passed after environment correction and portability fixes. |
| MIDI-B validation collection | missing | | | TCIA MIDI-B collection page | TCIA terms required | No local path, archive, answer key, mapping files, or validator package was supplied. |
| MIDI-B frozen test collection | missing | | | TCIA/Synapse challenge resources | terms required | Not supplied; final campaign blocked. |
| MIDI-B answer key and mapping files | missing | | | TCIA/Synapse challenge resources | terms required | Not supplied; import blocked. |
| Official MIDI-B validator | missing | | | TCIA/Synapse challenge resources | terms required | Not supplied; official parity blocked. |
| Orthanc | missing | | | Orthanc Docker documentation / Docker Hub | Orthanc/image license review required | No pinned image digest or running instance supplied. |
| RSNA DICOM Anonymizer | missing | | | RSNA imaging research tools / RSNA GitHub | license review required | No executable, version, project model, or hash supplied. |
| RSNA CTP | missing | | | RSNA MIRC CTP resources | RSNA terms/license review required | No CTP installation, JAR, version, or pipeline supplied. |
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
