# IOD-aware PS3.15 evaluation

The IOD-aware layer combines a user-local PS3.3-derived registry with the PS3.15 confidentiality-profile evaluator. It prevents a table-only evaluation from overlooking whether an attribute is valid or required in the active SOP Class/IOD.

## Legal and data model

The project does not redistribute PS3.3 tables or a full IOD registry. Users prepare a local registry from generated JSON obtained or generated separately. The project currently accepts a directory, ZIP, or wheel containing:

- `ciods.json`
- `sops.json`
- `ciod_to_modules.json`
- `module_to_attributes.json`

The preparation command records a source SHA-256 digest and creates one local normalized registry.

```bash
dicom-privacy-iod --edition local-2026c prepare-data \
  --source /path/to/generated-iod-json

dicom-privacy-iod --edition local-2026c info --json

dicom-privacy-iod --edition local-2026c sop 1.2.840.10008.5.1.4.1.1.7
```

Use environment variables when desired:

```bash
export DICOM_PRIVACY_IOD_DATA_DIR="$HOME/.local/share/dicom-privacy-auditor/iod"
export DICOM_PRIVACY_IOD_EDITION="local-2026c"
```

## Pair evaluation

Prepare PS3.15 data separately, then run:

```bash
dicom-privacy-ps315 evaluate source.dcm candidate.dcm \
  --iod-aware \
  --iod-registry /path/to/iod_registry_local-2026c.json \
  --json reports/ps315-iod.json \
  --csv reports/ps315-iod.csv
```

The context layer currently adds these checks:

- resolves SOP Class UID to a local Composite IOD;
- maps recursive tag paths to modules;
- identifies attributes absent from the active IOD;
- overrides undefined attributes to expected action `X`;
- prevents removal of Type 1 and Type 2 attributes;
- prevents zero-length values for Type 1 attributes;
- marks unresolved 1C/2C conditions for manual review; and
- flags candidate-only attributes not defined in the active IOD.

## Important limitations

This is **context-aware evaluation**, not a complete PS3.3 validator. In particular:

- complex conditional statements are not executed automatically;
- module inclusion conditions may require clinical or acquisition context;
- specialized and private SOP Classes require local definitions;
- standard extensions and retired objects may need additional registry data;
- a user-generated registry may contain extraction errors; and
- PS3.15 semantic cleaning and pixel requirements still require separate review.

Use a dedicated DICOM validator and independent standards review before claiming conformance.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
