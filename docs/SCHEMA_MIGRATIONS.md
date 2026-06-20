# Review database schema migrations

The current review database schema version is 2.

## Inspect

```bash
dicom-privacy-review schema-info review.db
```

## Upgrade

```bash
dicom-privacy-review migrate review.db
```

A timestamped byte-for-byte backup is created before migration. Use `--no-backup` only when another verified backup exists.

## Version 1 to version 2

The migration adds:

- `assigned_reviewer`
- numeric case `priority`
- `updated_at`
- `schema_migrations` ledger
- assignment/status index

Opening a version-1 database through `ReviewStore` performs the same migration. Databases with a schema version newer than the installed software are rejected rather than downgraded.
