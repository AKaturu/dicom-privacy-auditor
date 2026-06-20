# Contributing

## Safety first

Do not open issues, pull requests, screenshots, logs, fixtures, or examples containing real protected health information. Use only synthetic values. If sensitive information is accidentally committed, stop sharing the repository, rotate any exposed credentials, and follow the incident process in `SECURITY.md`.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"
make quality
# Before a release:
python scripts/run_local_release_gate.py . --output validation/local-release-gate.json
```

## Pull-request expectations

- Add tests for new rules and benchmark strata.
- Preserve redaction by default.
- Do not weaken safety language or imply regulatory certification.
- Document false-positive and false-negative risks.
- Keep generated test values obviously synthetic.
- Update both public and packaged schemas, examples, tests, and the changelog when output formats change; `check_schema_integrity.py` must pass.
- Freeze and report external tool versions in benchmark configurations.

## Adding a detection rule

A new rule should include:

1. the risk rationale;
2. severity and category;
3. a stable finding code;
4. a synthetic positive test;
5. a negative or clean-control test; and
6. limitations or likely confounders.

## Adding a benchmark stratum

Update the generator, manifest schema, evaluator, documentation, and end-to-end control expectations. The no-op must fail the new stratum, and the positive control must pass it before merge.
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [`docs/LEGAL_NOTICES.md`](docs/LEGAL_NOTICES.md).
