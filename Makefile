.PHONY: install test lint format-check typecheck security schemas workflows locks quality format samples audit ui benchmark benchmark-noop build distribution-check reproducible release-check clean

install:
	python -m pip install -e ".[dev,all,packaging]"

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p pytest_cov --cov=dicom_privacy_auditor --cov-report=term-missing --cov-fail-under=82

lint:
	ruff check .

format-check:
	ruff format --check .

typecheck:
	mypy

security:
	bandit -q -r src scripts -ll

schemas:
	python scripts/check_schema_integrity.py .

workflows:
	python scripts/check_action_pins.py
	python scripts/check_workflow_integrity.py .

locks:
	python scripts/check_dependency_locks.py .
	python -m pip check

quality: lint format-check typecheck security schemas workflows locks test

format:
	ruff format .

samples:
	python scripts/generate_synthetic_dicoms.py sample_data

audit:
	dicom-privacy-audit sample_data --pixel-scan --json reports/audit.json --csv reports/audit.csv

ui:
	streamlit run app.py

benchmark:
	dicom-privacy-benchmark all workspaces/baseline --pipeline baseline --overwrite

benchmark-noop:
	dicom-privacy-benchmark all workspaces/noop --pipeline noop --overwrite

build:
	python scripts/build_release_distributions.py . --output dist --clean

distribution-check: build
	python scripts/check_distribution_contents.py . dist

reproducible:
	python scripts/verify_reproducible_build.py .

release-check:
	python scripts/run_local_release_gate.py . --output validation/local-release-gate.json

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .hypothesis htmlcov .coverage build dist reports workspaces
