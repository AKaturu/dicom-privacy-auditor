# Security and release hardening

## Continuous integration

The repository includes:

- Python test matrix;
- benchmark-control smoke tests;
- distribution-content guard preventing standards redistribution;
- CodeQL Python analysis;
- `pip-audit` dependency scanning;
- Bandit static-security scanning;
- dependency-review enforcement on pull requests;
- Dependabot updates for Python and GitHub Actions; and
- explicit code ownership for security-sensitive modules.

## Release supply chain

Native release jobs:

- build on the target operating system;
- run tests and native smoke checks;
- create per-platform SHA-256 checksum files;
- generate a CycloneDX JSON SBOM;
- generate GitHub build-provenance attestations for public repositories;
- generate SBOM attestations for public repositories; and
- assemble a draft release for manual review.

Verify a public GitHub attestation with the GitHub CLI:

```bash
gh attestation verify DICOMPrivacyAuditor-RELEASE-ARCHIVE \
  --repo krishna2006sai/dicom-privacy-auditor
```

Checksums and attestations establish artifact integrity and build provenance. They do not replace Windows Authenticode signing or Apple Developer ID signing/notarization.

## Runtime boundaries

- Treat DICOM as untrusted input and run large-scale processing in a restricted service account or container.
- Do not run external adapters as an administrator/root user.
- Keep DICOMweb credentials in environment variables or a secret manager.
- Keep error-response bodies disabled unless debugging in a controlled environment.
- Apply network allowlists and TLS certificate validation.
- Keep source, quarantine, review databases, and logs off public storage.
- Rotate exposed credentials immediately.

## Remaining production controls

Before clinical deployment, add institution-managed code-signing identities, centralized audit logging, endpoint monitoring, backup/retention policy, formal penetration testing, and an institutional security/privacy review.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
