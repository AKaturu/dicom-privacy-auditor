# Native desktop and command-line executables

The release workflow builds self-contained executables. Users do not need to install Python.

## Distributed applications

Each operating-system archive contains:

- **DICOMPrivacyAuditor** — graphical privacy auditor for file or folder review.
- **DICOMPrivacyAuditor-CLI** — terminal application containing all project commands.
- `EXECUTABLE_README.txt` — launch examples, limitations, and checksum guidance.

The CLI is a multi-command executable:

```text
DICOMPrivacyAuditor-CLI audit <file-or-folder> [options]
DICOMPrivacyAuditor-CLI compare <source.dcm> <candidate.dcm> [options]
DICOMPrivacyAuditor-CLI deidentify <source.dcm> <destination.dcm> [options]
DICOMPrivacyAuditor-CLI benchmark <command> [options]
DICOMPrivacyAuditor-CLI review <command> [options]
DICOMPrivacyAuditor-CLI iod <command> [options]
DICOMPrivacyAuditor-CLI corpus <command> [options]
DICOMPrivacyAuditor-CLI dicomweb <command> [options]
DICOMPrivacyAuditor-CLI study <command> [options]
DICOMPrivacyAuditor-CLI campaign <command> [options]
```

## Local native build

PyInstaller embeds the current interpreter and operating-system-specific libraries. It is not a cross-compiler, so each native build must run on its target operating system.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[native]"
python scripts/build_executables.py
```

Artifacts are written to `dist/native`.

Native binaries expose review database creation, adjudication export, IOD/corpus evaluation, DICOMweb, study, and campaign commands. The browser-based review workstation itself requires the Python `ui` installation because Streamlit is intentionally omitted from the smaller native binary. Native binaries also omit the optional matplotlib plotting backend to keep downloads smaller; benchmark JSON, CSV, and Markdown outputs remain available. Install the Python `analysis` extra to generate PNG figures.

The dedicated native CLI intentionally does not duplicate the Tk desktop runtime. Launch `DICOMPrivacyAuditor` for the graphical interface; `DICOMPrivacyAuditor-CLI desktop` exits with an actionable message. Installed Python environments may still use `dicom-privacy desktop`.

## Automated cross-platform release build

The `build-native-release.yml` workflow builds on native GitHub-hosted runners for:

- Windows x64
- Linux x64
- macOS arm64 / Apple Silicon
- macOS x64 / Intel

Run the workflow manually from GitHub Actions or push a version tag such as `v0.7.1`. Each job performs a smoke test before uploading its archive. Tagged builds also create a draft GitHub Release containing archives, SHA-256 files, SBOMs, attestations, and per-platform `SIGNATURE-STATUS` records.

## macOS Gatekeeper

The generated `.app` is ad-hoc signed for structural integrity when Developer ID credentials are absent. When complete Apple credentials are configured, the workflow verifies Developer ID signing, submits for notarization, staples the ticket, and validates the staple. On first launch, an unsigned/not-notarized development build may require Control-click → Open. Production public distribution should use Developer ID signing and notarization.

## Windows reputation warnings

The generated `.exe` is Authenticode-signed and signature-verified only when the owner configures a certificate and password. Microsoft SmartScreen may warn about a new, low-reputation binary. Verify its SHA-256 checksum before running it.

## Clinical and privacy limitation

Executable packaging does not change the research status of the software. It is not a compliance certificate or clinical device, and reports should still be handled as potentially sensitive.
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
