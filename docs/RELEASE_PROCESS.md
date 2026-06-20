# Release process

## 1. Prepare and validate

Use a clean virtual environment and install the complete maintainer toolchain:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,all,packaging]" cyclonedx-bom
python scripts/run_local_release_gate.py . \
  --output validation/local-release-gate.json
```

Do not tag a release unless the report status is `passed`. A skipped reproducibility check creates a `partial` report and exits nonzero.

## 2. Build the source and Python distributions

```bash
SOURCE_DATE_EPOCH=1781913600 python scripts/build_release_distributions.py . --output dist --clean
SOURCE_DATE_EPOCH=1781913600 python scripts/package_source_release.py . \
  --output dist/dicom-privacy-auditor-v0.7.2-source.zip
python scripts/check_distribution_contents.py . dist
```

Generate the runtime SBOM from the canonical hashed lock rather than an unrelated shared environment:

```bash
python scripts/generate_runtime_sbom.py . \
  --output dist/SBOM-runtime.cdx.json
```

## 3. Assemble the migration bundle

Include the source ZIP, wheel, source distribution, SBOM, local gate report, completion report, and any exact-platform native archive. `assemble_release_bundle.py` creates a deterministic ZIP with `SHA256SUMS.txt` and a schema-validated `RELEASE-MANIFEST.json`.

## 4. Run native workflows

Push a version tag or dispatch `build-native-release.yml`. Each platform reruns quality gates, builds on its native runner, performs smoke tests, records SBOMs and provenance attestations, and writes a `SIGNATURE-STATUS-*.json` file. Windows Authenticode and Apple Developer ID/notarization are activated only when complete owner-controlled credentials are configured.

## 5. Preserve claim boundaries

Local gates do not establish complete MIDI-B performance, official-validator agreement, blinded-review results, institutional interoperability, regulatory compliance, or clinical suitability. Archive those results only after the corresponding external-validation preflight and authorized execution have been completed.
