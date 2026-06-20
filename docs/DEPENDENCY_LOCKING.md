# Dependency locking

The project distinguishes supported dependency ranges in `pyproject.toml` from a canonical, fully hashed validation environment.

## Canonical lock

`requirements/locks/cp313-linux-x86_64-runtime.txt` pins the complete runtime dependency graph for CPython 3.13 on Linux x86-64. CI installs it using both `--require-hashes` and `--only-binary=:all:` before installing the project with `--no-deps`.

The lock is not claimed to be portable to another Python minor version, operating system, or architecture. Platform-native release jobs should use a separately reviewed lock when strict artifact reproduction is required.

## Regeneration

Update `requirements/lock-input.txt`, then run:

```bash
python scripts/compile_lock.py \
  --output requirements/locks/cp313-linux-x86_64-runtime.txt
```

The script uses `uv pip compile --generate-hashes`. Review every version and hash change before merging. Do not hand-edit a hash to silence CI.

## Security policy

The supported Requests range starts at 2.33. A dependency update requires tests, the dependency-audit workflow, and a regenerated lock.
