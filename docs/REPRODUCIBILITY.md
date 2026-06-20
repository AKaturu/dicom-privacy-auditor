# Reproducibility

## Deterministic distribution check

```bash
python scripts/verify_reproducible_build.py .
```

The script copies the source into two clean temporary trees, sets a fixed `SOURCE_DATE_EPOCH` and `PYTHONHASHSEED`, builds a wheel and source distribution in each tree, normalizes source-distribution gzip/tar metadata, and requires identical SHA-256 digests for both artifact types.

## Research-run provenance

Benchmark, campaign, demonstration, and publication manifests record software versions and cryptographic hashes. Preserve these manifests with submitted tables and figures.

## JSON report validation

Schemas are installed as package resources. Schema-backed JSON is validated before an atomic temporary-file replacement. A failed validation therefore does not overwrite an existing valid report or leave a partial destination.

## Reproduction boundary

Reproducible software execution does not establish clinical generalizability. External MIDI-B validation, live-tool versions, configuration files, reviewer adjudication, and institutional environment details remain necessary for manuscript claims.

## Archive safety

Source-distribution normalization and distribution scanning reject unsafe paths, duplicate members, links/special entries, private keys, credential/database filenames, copyrighted standards source material, and excessive declared member or archive sizes. Release archives are created atomically with deterministic timestamps and permissions.
