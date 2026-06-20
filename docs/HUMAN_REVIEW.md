# Human review workstation

The workstation provides local, human-in-the-loop adjudication of paired source and candidate DICOM collections. It is intended for privacy quality assurance and research annotation, not public hosting.

## Create a paired review database

The source and candidate trees are matched by relative path.

```bash
dicom-privacy-review create \
  /data/source \
  /data/candidate \
  workspaces/review.sqlite \
  --title "MIDI-B Orthanc adjudication" \
  --overwrite
```

Only readable DICOM files present in both trees become review cases. The SQLite database stores local source/candidate paths and must be protected as sensitive operational data.

## Start blinded review

```bash
dicom-privacy-review serve workspaces/review.sqlite --port 8502
```

Blinding is enabled by default. A reviewer sees only their own prior decisions and does not see global case status. Use `--unblinded` only for adjudication or supervisory review.

The workstation includes:

- source/candidate image display;
- frame selection for multiframe objects;
- window center and width controls;
- recursive metadata differences;
- case-, metadata-, pixel-, and region-level decisions;
- optional pixel bounding boxes;
- reviewer comments and timestamps; and
- decisions requiring secondary review.

## Command-line adjudication

```bash
dicom-privacy-review summary workspaces/review.sqlite

dicom-privacy-review decide workspaces/review.sqlite CASE_ID \
  --reviewer reviewer-a \
  --scope region \
  --target burned-in-text \
  --status confirmed_identifier \
  --frame 0 \
  --region 10 20 300 80 \
  --comment "Synthetic patient name remains visible"
```

Allowed statuses are:

- `confirmed_identifier`
- `false_positive`
- `acceptable_retention`
- `needs_secondary_review`
- `not_reviewed`

## Dual review and agreement

```bash
dicom-privacy-review agreement \
  workspaces/review.sqlite reviewer-a reviewer-b
```

The result includes matched targets, exact agreement, Cohen's kappa, confusion counts, and unmatched decisions.

## Export

```bash
dicom-privacy-review export \
  workspaces/review.sqlite reports/review.json
```

Paths are redacted by default. JSON exports include the SHA-256 digest of the SQLite database at export time. This provides a useful integrity reference but is not a digital signature. Comments may contain sensitive information entered by reviewers and must still be reviewed before external release.

## Safety boundaries

- Run the workstation on a trusted local machine or protected institutional network.
- Do not expose Streamlit directly to the public internet.
- Do not assume a completed review proves legal or regulatory compliance.
- Human review complements, rather than replaces, automated metadata, pixel, and corpus checks.
- Full absence of visible text does not establish that recognizable facial or anatomical features have been removed.

---

DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. See [Legal notices](LEGAL_NOTICES.md).

## Integrity and adjudication packets

Check database structure and foreign keys before export or adjudication:

```bash
dicom-privacy-review integrity-check workspaces/review.sqlite
```

Create a packet containing only reviewer disagreements and unmatched targets:

```bash
dicom-privacy-review disagreements \
  workspaces/review.sqlite reviewer-a reviewer-b \
  --output reports/adjudication.json
```

The packet is validated against `review-disagreements.schema.json`, uses each reviewer's latest decision for a target, and is created with owner-only permissions on platforms that support POSIX modes. An adjudicator can resolve each item with the existing `decide` command under a distinct coded reviewer name.

## Review UI network binding

The review UI binds to `127.0.0.1` by default. Binding to another address requires an explicit acknowledgement:

```bash
dicom-privacy-review serve workspaces/review.sqlite \
  --address 10.0.0.15 --allow-network
```

A non-loopback bind does not add authentication, authorization, TLS, or a reverse proxy. Use it only inside an appropriately protected institutional environment.
