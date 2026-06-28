# Demo Media

The repository includes a short synthetic demo animation for GitHub:

- `docs/assets/demo-poster.png`
- `docs/assets/demo.gif`
- `docs/assets/demo.mp4`

The footage is generated from the real `dicom-privacy-demo` command. It creates synthetic DICOM objects, runs the built-in benchmark controls, evaluates seeded residual identifiers, and writes review/publication artifacts. It does not include real patient data and is not a compliance certificate.

## Regenerate

```bash
python -m pip install -e ".[analysis,media]"
python scripts/generate_demo_media.py
```

The script writes a temporary workspace under `outputs/demo-media/`, extracts `summary.json` and `demo_manifest.json`, and renders the committed media files under `docs/assets/`.
