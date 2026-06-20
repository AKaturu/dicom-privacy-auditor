# Manuscript-ready report generation

```bash
dicom-privacy-report generate WORKSPACE OUTPUT \
  --title "Standards-based DICOM de-identification evaluation" \
  --review-db WORKSPACE/human-review.db
```

Absolute workspace and input paths are redacted by default. Add `--disclose-paths` only when the package will remain in an approved restricted environment.

## Outputs

- overall performance table in CSV and LaTeX
- performance-by-stratum table in CSV and LaTeX
- exact paired-comparison table
- reviewer-agreement table when two reviewers are available
- `MANUSCRIPT_REPORT.md`
- `METHODS_TEMPLATE.md`
- `REPRODUCIBILITY_APPENDIX.md`
- optional PNG figure
- `publication_manifest.json` with SHA-256 input/output provenance and a path-disclosure flag

## Guardrails

The generator reports what is present in the workspace. It does not infer missing human-review results, substitute synthetic results for MIDI-B results, or certify compliance. Generated prose must be checked against the study protocol, frozen primary endpoint, and final statistical analysis before submission.

Generated directories and files use owner-only permissions where the operating system supports them. This protects local drafts; it does not replace institutional storage, access control, or retention policy.
