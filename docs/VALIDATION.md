# Validation and Interpretation

## What a finding means

A finding is a review signal produced by a transparent rule. It is not a legal conclusion and does not prove that the object is identifying in the recipient's context.

## What zero findings means

Zero findings only means that none of the configured rules fired. It does not establish that:

- every DICOM PS3.15 action was applied;
- pixels are clean;
- private semantics are safe;
- companion files are clean;
- re-identification risk is acceptable; or
- the release complies with law or policy.

## Basic DICOM validation

The repository checks readability, key SOP/file-meta consistency, transfer-syntax presence, and pixel-module completeness. It is not a substitute for a complete IOD validator such as a dedicated DICOM validation tool.

## Pixel scan

The pixel scan measures dense high-contrast edges near borders. It is deliberately labeled experimental. It can miss text, flag anatomy or collimation edges, and cannot read the content. Human review or validated OCR/segmentation remains necessary.

## Ground-truth limitations

Exact synthetic tokens provide precise ground truth but do not capture every transformation. A tool that partially masks, transliterates, hashes, or semantically paraphrases a value may require additional matching logic and manual adjudication.

## Statistical interpretation

Wilson confidence intervals quantify binomial uncertainty. McNemar testing compares paired binary outcomes on shared injections. Neither addresses clustering across objects, modalities, institutions, or vendors. A larger clinical validation should use clustered or mixed-effects methods where appropriate.
---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).
