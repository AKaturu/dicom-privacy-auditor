# External Pipeline Adapters

## One-file command contract

The adapter invokes one command per source object without `shell=True`. The command must create the requested output file and return zero.

```bash
dicom-privacy-benchmark run benchmark run-mytool \
  --external-name mytool-1.2.3 \
  --external-command mytool --input "{input}" --output "{output}" \
  --output-name-mode preserve
```

Available placeholders:

- `{input}` — absolute source path
- `{output}` — absolute expected output path
- `{output_dir}` — parent directory for the output
- `{case_id}` — synthetic case identifier
- `{input_name}` — source filename

## Filename policy

- `preserve`: output target uses the original benchmark filename, allowing filename leakage to remain measurable.
- `safe`: output target uses `<case_id>.dcm`. This should be described as wrapper- or adapter-assisted filename cleaning.

## Wrapper recommendation

Complex tools should be wrapped by a small script that:

1. accepts one input and one output path;
2. freezes the tool version and configuration;
3. returns nonzero on failure;
4. writes logs outside the DICOM output tree; and
5. does not copy artificial values into filenames or console logs.

## Multi-instance workflows

Tools requiring a full study or directory should use a study-level wrapper. Preserve the benchmark case mapping in `run_manifest.json`, and document any filename or directory transformations performed by the wrapper.
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
