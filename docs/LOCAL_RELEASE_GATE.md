# Local release gate

`dicom-privacy-auditor` includes one command that runs every release check that does not require an external dataset, live service, independent reviewer, platform-specific runner, or signing credential:

```bash
python scripts/run_local_release_gate.py . \
  --output validation/local-release-gate.json
```

The gate runs immutable GitHub Action pin checks, workflow YAML validation, schema/configuration integrity, dependency-lock consistency, `pip check`, Ruff lint and formatting, Python compilation, mypy, Bandit medium/high findings, the full test and coverage suite, wheel/source builds, distribution policy checks, and the byte-for-byte reproducible wheel and normalized-sdist test. It records command output tails, return codes, durations, and the local platform in a machine-readable JSON report. Project, temporary, home, Python-environment, and other absolute paths are redacted from captured output. The gate report is written with owner-only permissions.

A report is `passed` only when every check runs and succeeds. `--skip-reproducible` exists for rapid development but produces a `partial` report and a nonzero exit status, so it cannot be confused with a complete release gate.

The local gate does **not** claim completion of MIDI-B, live Orthanc/RSNA, institutional DICOMweb/PACS, independent blinded review, Windows/macOS execution, code signing, or notarization. Those are tracked separately by the external-validation preflight and platform workflows.
