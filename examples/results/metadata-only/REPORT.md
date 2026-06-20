# Benchmark Evaluation: metadata-only

## Summary

- Cases: 60
- Injected identifiers: 50
- Removal rate: 0.800
- Residual identifiers: 10
- Auditor sensitivity among residuals: 1.0
- Clean-control false-positive rate: 0.000
- Basic-valid outputs: 60/60
- Mean runtime per object: 0.002090 seconds

## Performance by stratum

| Stratum | N | Removed | Residual | Removal rate | Auditor sensitivity on residuals |
|---|---:|---:|---:|---:|---:|
| file_meta | 5 | 5 | 0 | 1.000 | NA |
| filename | 5 | 0 | 5 | 0.000 | 1.000 |
| free_text | 5 | 5 | 0 | 1.000 | NA |
| nested_sequence | 5 | 5 | 0 | 1.000 | NA |
| pixel_annotation | 5 | 0 | 5 | 0.000 | 1.000 |
| preamble | 5 | 5 | 0 | 1.000 | NA |
| private_attribute | 5 | 5 | 0 | 1.000 | NA |
| standard_metadata | 5 | 5 | 0 | 1.000 | NA |
| temporal | 5 | 5 | 0 | 1.000 | NA |
| uid | 5 | 5 | 0 | 1.000 | NA |
