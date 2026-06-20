# Benchmark Evaluation: orthanc

## Summary

- Cases: 12
- Injected identifiers: 10
- Removal rate: 0.900
- Residual identifiers: 1
- Auditor sensitivity among residuals: 1.0
- Clean-control false-positive rate: 1.000
- Basic-valid outputs: 12/12
- Mean runtime per object: 0.366081 seconds

## Performance by stratum

| Stratum | N | Removed | Residual | Removal rate | Auditor sensitivity on residuals |
|---|---:|---:|---:|---:|---:|
| file_meta | 1 | 1 | 0 | 1.000 | NA |
| filename | 1 | 1 | 0 | 1.000 | NA |
| free_text | 1 | 1 | 0 | 1.000 | NA |
| nested_sequence | 1 | 1 | 0 | 1.000 | NA |
| pixel_annotation | 1 | 0 | 1 | 0.000 | 1.000 |
| preamble | 1 | 1 | 0 | 1.000 | NA |
| private_attribute | 1 | 1 | 0 | 1.000 | NA |
| standard_metadata | 1 | 1 | 0 | 1.000 | NA |
| temporal | 1 | 1 | 0 | 1.000 | NA |
| uid | 1 | 1 | 0 | 1.000 | NA |
