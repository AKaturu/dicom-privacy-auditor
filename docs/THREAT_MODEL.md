# Threat Model

## Assets

- Patient, personnel, institution, and device identity
- Longitudinal linkage keys and reversible pseudonym maps
- Source filenames, directory structures, and object-store keys
- Study/series/instance relationships and date offsets
- Review databases, reviewer decisions, screenshots, and audit trails
- DICOMweb, Orthanc, DIMSE, and container credentials
- Campaign configurations, manifests, reports, logs, and CI artifacts

## Adversaries and failure modes

- An external recipient attempting re-identification
- An internal user with access to both original and de-identified datasets
- A compromised DICOMweb/PACS/de-identification endpoint
- A repository contributor who accidentally commits identifiers, secrets, or copyrighted standards content
- A workflow operator who assumes metadata-only cleaning covers pixels, sidecars, references, and filesystems
- A malicious or malformed DICOM object intended to trigger parser/resource-exhaustion behavior
- A supply-chain attacker introducing a vulnerable dependency or substituted binary

## Leakage channels considered

- Standard attributes and nested sequences
- Private elements and creators
- Free text, dates, times, UIDs, pseudonyms, and cross-object references
- File Meta Information and preambles
- Filenames, paths, object-store keys, logs, reports, and quarantine locations
- Pixel annotations and recognizable visual features
- Structured Reports, overlays, graphics, Original Attributes Sequence, signatures, and embedded documents as review signals
- Review annotations and corpus-level mapping evidence

## Leakage channels not fully solved

- Facial reconstruction and recognizable anatomy
- Natural-language semantic re-identification after paraphrase
- Compressed or multiframe OCR across every transfer syntax
- Complete encapsulated-document parsing
- Private SOP classes and proprietary sidecars
- Cloud-provider metadata, backups, temporary files, swap, and endpoint telemetry
- Membership inference or model memorization
- Malicious file sandboxing

## Report and review-generation risk

An auditor can create a new privacy leak by copying raw identifiers or linked paths into reports. This project redacts values and paths by default and stores short one-way digests where comparison is necessary. `--show-values` is explicitly unsafe and intended only for controlled local debugging. Review databases and exports are sensitive even when redacted because decisions, hashes, timestamps, and pairings can disclose relationships.

## Network risk

DICOMweb and adapter workflows move complete studies across trust boundaries. HTTPS and certificate verification are required by default for DICOMweb. Literal credentials are rejected unless explicitly allowed. Operators remain responsible for endpoint authorization, mTLS where required, network segmentation, request-size controls, audit logs, secret management, and destination governance.

## Atomicity and partial-study risk

A partially processed or partially uploaded study can break referential integrity or mix source and candidate objects. Study workflows stage outputs, validate collection consistency, quarantine failures, and commit only complete studies by default. `--commit-partial` is an explicit research-only escape hatch.

## Pseudonymization risk

The built-in UID mapper is deterministic and uses a public benchmark salt by default. It is not suitable as a production secret or reversible mapping system. Production deployments require governed key management, access controls, rotation, recovery procedures, collision monitoring, and a documented linkage scope.

## Supply-chain risk

Checksums, SBOMs, dependency review, static analysis, and artifact attestations improve traceability but do not prove clinical safety or absence of compromise. Production releases should use signed tags, pinned action SHAs, platform code signing, macOS notarization, independent checksum verification, and a documented key-compromise response.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
