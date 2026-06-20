# Security and Privacy Policy

## Reporting vulnerabilities

Report software vulnerabilities privately to the repository owner rather than opening a public issue. Include the affected version, reproduction steps using synthetic data, and potential impact. Do not attach real DICOM objects or PHI.

## Protected-data incidents

Do not submit real PHI or other sensitive personal information to issues, pull requests, CI artifacts, review exports, or campaign bundles. If sensitive data are exposed:

1. stop further distribution;
2. remove public access where possible;
3. preserve only the minimum incident evidence in an approved location;
4. notify the appropriate institutional privacy/security office;
5. rotate exposed credentials, tokens, pseudonymization keys, or mappings; and
6. follow institutional breach-response procedures.

## Supported versions

Security and privacy fixes are applied to the latest tagged release and the default branch.

## Network and credential controls

- DICOMweb requires HTTPS by default. Disabling TLS verification requires an explicit unsafe override, redirects are refused, and authenticated endpoints must use HTTPS.
- Remote authenticated Orthanc endpoints must use HTTPS; plaintext access is limited to deliberate anonymous use or loopback development.
- Authentication should be supplied through environment variables; literal authorization headers are rejected by default.
- Study uploads are all-or-nothing by default. Failed or incomplete studies are quarantined instead of committed.
- Adapter and campaign manifests hash configurations but must still be treated as potentially sensitive.
- The review workstation binds to loopback by default; non-loopback binding requires an explicit `--allow-network` acknowledgement.
- Production services should enforce network allowlists, least-privilege service accounts, certificate validation, request limits, and institutional audit logging.

## Review-workstation controls

Review databases and exports can reveal that two datasets are linked even when values and paths are redacted. Store them in approved locations, restrict access, define retention periods, and avoid public synchronization. Reviewer identifiers should be coded rather than directly identifying whenever feasible.

## Supply-chain controls

The repository includes CodeQL, dependency audit, Bandit, mypy, dependency review, Dependabot, schema/configuration checks, hashed-lock consistency, SBOM generation, deterministic packaging, distribution-content scanning, and GitHub artifact attestations. Public native binaries are still development artifacts unless platform signing and notarization are configured and independently verified.

## Known security boundaries

- The tool does not sandbox malicious DICOM files or third-party de-identification tools.
- External commands execute with the invoking user's permissions.
- The default benchmark UID salt is public and is not a production secret.
- Audit paths, hashes, study UIDs, timestamps, review decisions, and linkage evidence can be sensitive.
- `--show-values` may disclose identifiers in logs and output files.
- OCR and visual-recognition providers are review aids, not proof that pixels are free of identifying content.
- DICOMweb, Orthanc, DIMSE, filesystem, and container integrations inherit the security properties of their deployment environments.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [`docs/LEGAL_NOTICES.md`](docs/LEGAL_NOTICES.md).
