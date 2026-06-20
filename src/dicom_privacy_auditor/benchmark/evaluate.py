from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pydicom

from ..audit import audit_file, walk_dataset
from ..compare import compare_files
from ..detectors import normalize_value
from ..jsonio import write_json
from ..models import SEVERITY_ORDER
from ..permissions import restrict_directory, restrict_file
from ..pixel import patch_similarity
from .manifest import BenchmarkManifest, Injection
from .runner import RunManifest, contained_path

DETECTION_CODES: dict[str, set[str]] = {
    "standard_metadata": {"DIRECT_IDENTIFIER_PRESENT", "SOURCE_VALUE_RETAINED"},
    "nested_sequence": {"DIRECT_IDENTIFIER_PRESENT", "IDENTIFIER_PATTERN_IN_TEXT", "SOURCE_VALUE_RETAINED"},
    "private_attribute": {"PRIVATE_ATTRIBUTE_PRESENT", "SOURCE_VALUE_RETAINED"},
    "free_text": {"IDENTIFIER_PATTERN_IN_TEXT", "SOURCE_VALUE_RETAINED"},
    "filename": {"FILENAME_REVIEW"},
    "temporal": {"SOURCE_DATE_UNCHANGED", "DATE_TIME_PRESENT"},
    "uid": {"SOURCE_UID_UNCHANGED"},
    "pixel_annotation": {
        "PIXEL_REVIEW_REQUIRED",
        "PIXEL_TEXT_LIKE_REGION",
        "PIXEL_DATA_UNCHANGED_WITH_ANNOTATION_RISK",
    },
    "file_meta": {"FILE_META_IDENTITY_PRESENT", "SOURCE_VALUE_RETAINED"},
    "preamble": {"NONZERO_PREAMBLE_REVIEW"},
}


@dataclass
class InjectionResult:
    pipeline: str
    case_id: str
    injection_id: str
    stratum: str
    output_present: bool
    residual: bool
    removed: bool
    auditor_detected: bool
    finding_codes: list[str]
    similarity: float | None = None
    error: str | None = None


@dataclass
class CaseEvaluation:
    pipeline: str
    case_id: str
    clean_control: bool
    output_present: bool
    readable: bool
    valid_basic: bool
    runtime_seconds: float
    high_or_critical_findings: int
    injections: list[InjectionResult]
    error: str | None = None


@dataclass
class BenchmarkEvaluation:
    pipeline: str
    benchmark_name: str
    cases: list[CaseEvaluation]
    summary: dict[str, Any]
    by_stratum: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "benchmark_name": self.benchmark_name,
            "summary": self.summary,
            "by_stratum": self.by_stratum,
            "cases": [
                {
                    **{key: value for key, value in asdict(case).items() if key != "injections"},
                    "injections": [asdict(item) for item in case.injections],
                }
                for case in self.cases
            ],
        }


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def _dataset_contains(dataset, value: str) -> bool:
    for _, element in walk_dataset(dataset):
        if element.VR == "SQ":
            continue
        if value and value in normalize_value(element.value):
            return True
    file_meta = getattr(dataset, "file_meta", None)
    if file_meta:
        for _, element in walk_dataset(file_meta, prefix="file_meta"):
            if value and value in normalize_value(element.value):
                return True
    return False


def _pixel_residual(
    original_path: Path,
    candidate_path: Path,
    injection: Injection,
) -> tuple[bool, float | None, str | None]:
    if not injection.bbox_xyxy:
        return True, None, "Missing benchmark bounding box"
    try:
        original = np.asarray(pydicom.dcmread(original_path).pixel_array)
        candidate = np.asarray(pydicom.dcmread(candidate_path).pixel_array)
    except Exception as exc:
        return True, None, f"Pixel decoding failed: {type(exc).__name__}: {exc}"
    if original.shape != candidate.shape or original.ndim != 2:
        return True, None, f"Pixel shape changed from {original.shape} to {candidate.shape}"
    x1, y1, x2, y2 = [int(value) for value in injection.bbox_xyxy]
    original_patch = original[y1:y2, x1:x2]
    candidate_patch = candidate[y1:y2, x1:x2]
    similarity = patch_similarity(original_patch, candidate_patch)
    candidate_range = float(np.ptp(candidate_patch)) if candidate_patch.size else 0.0
    # Compression-tolerant: correlation plus remaining local contrast.
    residual = similarity >= 0.80 and candidate_range >= 20
    return residual, similarity, None


def _is_residual(
    original_path: Path,
    candidate_path: Path,
    injection: Injection,
) -> tuple[bool, float | None, str | None]:
    if not candidate_path.exists():
        return True, None, "Output missing"
    if injection.location_kind == "filename":
        return injection.value.lower() in candidate_path.name.lower(), None, None
    if injection.location_kind == "preamble":
        try:
            data = candidate_path.read_bytes()[:128]
            return injection.value.encode("ascii") in data, None, None
        except OSError as exc:
            return True, None, str(exc)
    if injection.location_kind == "pixel_bbox":
        return _pixel_residual(original_path, candidate_path, injection)
    try:
        dataset = pydicom.dcmread(candidate_path)
    except Exception as exc:
        return True, None, f"Candidate unreadable: {type(exc).__name__}: {exc}"
    return _dataset_contains(dataset, injection.value), None, None


def _auditor_findings(original_path: Path, candidate_path: Path, *, paired: bool = True) -> list:
    standalone = audit_file(candidate_path, inspect_pixels=True, include_dates=True)
    if not paired:
        return standalone.findings
    comparison = compare_files(original_path, candidate_path)
    return standalone.findings + comparison.findings


def evaluate_run(
    benchmark_dir: str | Path,
    run_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> BenchmarkEvaluation:
    benchmark_root = Path(benchmark_dir).resolve()
    run_root = Path(run_dir).resolve()
    manifest = BenchmarkManifest.read(benchmark_root / "manifest.json")
    run_manifest = RunManifest.read(run_root / "run_manifest.json")
    run_by_case = {case.case_id: case for case in run_manifest.cases}
    expected_case_ids = {case.case_id for case in manifest.cases}
    unknown_case_ids = sorted(set(run_by_case) - expected_case_ids)
    if unknown_case_ids:
        raise ValueError(f"run manifest contains unknown benchmark cases: {unknown_case_ids}")
    evaluations: list[CaseEvaluation] = []

    for case in manifest.cases:
        run_case = run_by_case.get(case.case_id)
        if run_case and run_case.input_relative_path != case.relative_path:
            raise ValueError(f"run manifest input path mismatch for case {case.case_id}")
        original_path = contained_path(benchmark_root, case.relative_path, label="benchmark input")
        candidate_path = (
            contained_path(run_root, run_case.output_relative_path, label="benchmark output")
            if run_case and run_case.output_relative_path
            else None
        )
        output_present = bool(candidate_path and candidate_path.exists())
        readable = bool(run_case and run_case.validation and run_case.validation.get("readable"))
        valid_basic = bool(run_case and run_case.validation and run_case.validation.get("valid_basic"))
        findings = (
            _auditor_findings(original_path, candidate_path, paired=not case.clean_control)
            if candidate_path and candidate_path.exists()
            else []
        )
        finding_codes = sorted({finding.code for finding in findings})
        high_or_critical = sum(
            SEVERITY_ORDER.get(finding.severity, 0) >= SEVERITY_ORDER["high"] for finding in findings
        )
        injection_results: list[InjectionResult] = []

        for injection in case.injections:
            is_residual: bool
            similarity: float | None
            residual_error: str | None
            if not candidate_path:
                is_residual, similarity, residual_error = True, None, "Output missing"
            else:
                is_residual, similarity, residual_error = _is_residual(
                    original_path, candidate_path, injection
                )
            acceptable = DETECTION_CODES.get(injection.stratum, set())
            detected = is_residual and any(code in acceptable for code in finding_codes)
            injection_results.append(
                InjectionResult(
                    pipeline=run_manifest.pipeline_name,
                    case_id=case.case_id,
                    injection_id=injection.injection_id,
                    stratum=injection.stratum,
                    output_present=output_present,
                    residual=is_residual,
                    removed=not is_residual,
                    auditor_detected=detected,
                    finding_codes=finding_codes,
                    similarity=similarity,
                    error=residual_error,
                )
            )

        evaluations.append(
            CaseEvaluation(
                pipeline=run_manifest.pipeline_name,
                case_id=case.case_id,
                clean_control=case.clean_control,
                output_present=output_present,
                readable=readable,
                valid_basic=valid_basic,
                runtime_seconds=run_case.runtime_seconds if run_case else 0.0,
                high_or_critical_findings=high_or_critical,
                injections=injection_results,
                error=run_case.error if run_case else "Case missing from run manifest",
            )
        )

    all_injections = [item for case in evaluations for item in case.injections]
    removed = sum(item.removed for item in all_injections)
    residual_count = sum(item.residual for item in all_injections)
    detected_count = sum(item.auditor_detected for item in all_injections if item.residual)
    controls = [case for case in evaluations if case.clean_control]
    false_positive_controls = sum(case.high_or_critical_findings > 0 for case in controls)
    valid_cases = sum(case.valid_basic for case in evaluations)
    readable_cases = sum(case.readable for case in evaluations)
    total_runtime = sum(case.runtime_seconds for case in evaluations)
    removal_ci = _wilson(removed, len(all_injections))
    detection_ci = _wilson(detected_count, residual_count)
    fp_ci = _wilson(false_positive_controls, len(controls))

    summary = {
        "cases": len(evaluations),
        "injections": len(all_injections),
        "removed_injections": removed,
        "residual_injections": residual_count,
        "removal_rate": removed / len(all_injections) if all_injections else 0.0,
        "removal_rate_ci95": list(removal_ci),
        "auditor_detected_residuals": detected_count,
        "auditor_residual_sensitivity": detected_count / residual_count if residual_count else None,
        "auditor_residual_sensitivity_ci95": list(detection_ci) if residual_count else None,
        "clean_controls": len(controls),
        "false_positive_controls": false_positive_controls,
        "false_positive_control_rate": false_positive_controls / len(controls) if controls else 0.0,
        "false_positive_control_rate_ci95": list(fp_ci),
        "readable_outputs": readable_cases,
        "basic_valid_outputs": valid_cases,
        "total_runtime_seconds": total_runtime,
        "mean_runtime_seconds": total_runtime / len(evaluations) if evaluations else 0.0,
    }

    by_stratum: list[dict[str, Any]] = []
    strata = sorted({item.stratum for item in all_injections})
    for stratum in strata:
        items = [item for item in all_injections if item.stratum == stratum]
        n_removed = sum(item.removed for item in items)
        n_residual = sum(item.residual for item in items)
        n_detected = sum(item.auditor_detected for item in items if item.residual)
        ci = _wilson(n_removed, len(items))
        by_stratum.append(
            {
                "stratum": stratum,
                "injections": len(items),
                "removed": n_removed,
                "residual": n_residual,
                "removal_rate": n_removed / len(items) if items else 0.0,
                "removal_rate_ci95_low": ci[0],
                "removal_rate_ci95_high": ci[1],
                "auditor_detected_residuals": n_detected,
                "auditor_residual_sensitivity": n_detected / n_residual if n_residual else None,
            }
        )

    evaluation = BenchmarkEvaluation(
        pipeline=run_manifest.pipeline_name,
        benchmark_name=manifest.benchmark_name,
        cases=evaluations,
        summary=summary,
        by_stratum=by_stratum,
    )
    if output_dir is not None:
        write_evaluation(evaluation, output_dir)
    return evaluation


def write_evaluation(evaluation: BenchmarkEvaluation, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    restrict_directory(output)
    write_json(output / "evaluation.json", evaluation.to_dict(), schema_name="evaluation")

    with (output / "injection_results.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = (
            list(asdict(next(item for case in evaluation.cases for item in case.injections)).keys())
            if any(case.injections for case in evaluation.cases)
            else []
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for case in evaluation.cases:
                for item in case.injections:
                    row = asdict(item)
                    row["finding_codes"] = "|".join(row["finding_codes"])
                    writer.writerow(row)
    restrict_file(output / "injection_results.csv")

    with (output / "stratum_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(evaluation.by_stratum[0].keys()) if evaluation.by_stratum else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(evaluation.by_stratum)
    restrict_file(output / "stratum_metrics.csv")

    lines = [
        f"# Benchmark Evaluation: {evaluation.pipeline}",
        "",
        "## Summary",
        "",
        f"- Cases: {evaluation.summary['cases']}",
        f"- Injected identifiers: {evaluation.summary['injections']}",
        f"- Removal rate: {evaluation.summary['removal_rate']:.3f}",
        f"- Residual identifiers: {evaluation.summary['residual_injections']}",
        f"- Auditor sensitivity among residuals: {evaluation.summary['auditor_residual_sensitivity']}",
        f"- Clean-control false-positive rate: {evaluation.summary['false_positive_control_rate']:.3f}",
        f"- Basic-valid outputs: {evaluation.summary['basic_valid_outputs']}/{evaluation.summary['cases']}",
        f"- Mean runtime per object: {evaluation.summary['mean_runtime_seconds']:.6f} seconds",
        "",
        "## Performance by stratum",
        "",
        "| Stratum | N | Removed | Residual | Removal rate | Auditor sensitivity on residuals |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in evaluation.by_stratum:
        sensitivity = row["auditor_residual_sensitivity"]
        sensitivity_text = "NA" if sensitivity is None else f"{sensitivity:.3f}"
        lines.append(
            f"| {row['stratum']} | {row['injections']} | {row['removed']} | {row['residual']} | "
            f"{row['removal_rate']:.3f} | {sensitivity_text} |"
        )
    report_path = output / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    restrict_file(report_path)


def mcnemar_exact(evaluation_a: BenchmarkEvaluation, evaluation_b: BenchmarkEvaluation) -> dict[str, Any]:
    a = {item.injection_id: item.removed for case in evaluation_a.cases for item in case.injections}
    b = {item.injection_id: item.removed for case in evaluation_b.cases for item in case.injections}
    shared = sorted(set(a) & set(b))
    b_only = sum((not a[key]) and b[key] for key in shared)
    a_only = sum(a[key] and (not b[key]) for key in shared)
    discordant = a_only + b_only
    if discordant == 0:
        p_value = 1.0
    else:
        smaller = min(a_only, b_only)
        tail = sum(math.comb(discordant, k) for k in range(smaller + 1)) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {
        "pipeline_a": evaluation_a.pipeline,
        "pipeline_b": evaluation_b.pipeline,
        "shared_injections": len(shared),
        "a_removed_b_failed": a_only,
        "b_removed_a_failed": b_only,
        "discordant_pairs": discordant,
        "two_sided_exact_p": p_value,
    }
