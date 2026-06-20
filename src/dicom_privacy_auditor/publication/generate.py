from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from ..jsonio import write_json
from ..permissions import restrict_directory, restrict_file
from ..review.store import ReviewStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _escape(value: Any) -> str:
    return (
        str(value)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
    )


def _write_table(rows: list[dict[str, Any]], stem: Path) -> list[Path]:
    if not rows:
        return []
    fields = list(rows[0])
    csv_path = stem.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    restrict_directory(csv_path.parent)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tex_path = stem.with_suffix(".tex")
    alignment = "l" + "r" * (len(fields) - 1)
    lines = [
        f"\\begin{{tabular}}{{{alignment}}}",
        "\\hline",
        " & ".join(_escape(x) for x in fields) + r" \\",
        "\\hline",
    ]
    for row in rows:
        lines.append(" & ".join(_escape(row.get(field, "")) for field in fields) + r" \\")
    lines += ["\\hline", "\\end{tabular}"]
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    restrict_file(csv_path)
    restrict_file(tex_path)
    return [csv_path, tex_path]


def _load_evaluations(workspace: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(workspace.glob("evaluation-*/evaluation.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_source"] = str(path)
        payloads.append(payload)
    return payloads


def generate_publication_package(
    workspace: str | Path,
    output_dir: str | Path,
    *,
    title: str = "DICOM de-identification benchmark report",
    review_database: str | Path | None = None,
    disclose_paths: bool = False,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    restrict_directory(output)
    evaluations = _load_evaluations(workspace_path)
    if not evaluations:
        raise FileNotFoundError(f"No evaluation-*/evaluation.json files found under {workspace_path}")

    overall: list[dict[str, Any]] = []
    strata: list[dict[str, Any]] = []
    input_paths: list[Path] = []
    for payload in evaluations:
        source = Path(payload.pop("_source"))
        input_paths.append(source)
        summary = payload["summary"]
        ci = summary.get("removal_rate_ci95", [None, None])
        overall.append(
            {
                "pipeline": payload["pipeline"],
                "cases": summary["cases"],
                "injections": summary["injections"],
                "removed": summary["removed_injections"],
                "residual": summary["residual_injections"],
                "removal_rate": f"{summary['removal_rate']:.4f}",
                "ci95_low": "" if ci[0] is None else f"{ci[0]:.4f}",
                "ci95_high": "" if ci[1] is None else f"{ci[1]:.4f}",
                "valid_outputs": summary["basic_valid_outputs"],
                "mean_runtime_seconds": f"{summary['mean_runtime_seconds']:.6f}",
            }
        )
        for row in payload.get("by_stratum", []):
            strata.append({"pipeline": payload["pipeline"], **row})

    comparison_path = workspace_path / "paired_comparisons.json"
    comparisons = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path.exists() else {}
    if comparison_path.exists():
        input_paths.append(comparison_path)
    comparison_rows = [{"comparison": key, **value} for key, value in comparisons.items()]

    review_rows: list[dict[str, Any]] = []
    review_summary: dict[str, Any] | None = None
    if review_database:
        store = ReviewStore(review_database)
        review_summary = store.summary()
        reviewers = review_summary.get("reviewers", [])
        if len(reviewers) >= 2:
            agreement = store.agreement(reviewers[0], reviewers[1]).to_dict()
            review_rows.append(agreement)
        input_paths.append(Path(review_database))

    generated: list[Path] = []
    generated += _write_table(overall, output / "tables" / "table_overall")
    generated += _write_table(strata, output / "tables" / "table_by_stratum")
    generated += _write_table(comparison_rows, output / "tables" / "table_paired_comparisons")
    generated += _write_table(review_rows, output / "tables" / "table_reviewer_agreement")

    methods = [
        "# Methods template",
        "",
        f"This analysis was generated with DICOM Privacy Auditor {__version__}.",
        f"The benchmark contained {overall[0]['cases']} cases and {overall[0]['injections']} seeded synthetic identifiers.",
        "Each pipeline was evaluated using identical case identifiers. Identifier-removal proportions are accompanied by Wilson 95% confidence intervals. Paired pipeline differences use an exact McNemar test.",
        "This automatically generated text must be reviewed and edited before manuscript submission. It does not establish clinical safety, HIPAA compliance, or DICOM conformance.",
    ]
    methods_path = output / "METHODS_TEMPLATE.md"
    methods_path.write_text("\n\n".join(methods) + "\n", encoding="utf-8")
    generated.append(methods_path)

    report = [
        f"# {title}",
        "",
        "## Results",
        "",
        "| Pipeline | Removed / N | Removal rate (95% CI) | Residual | Valid outputs |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in overall:
        report.append(
            f"| {row['pipeline']} | {row['removed']} / {row['injections']} | {row['removal_rate']} ({row['ci95_low']}–{row['ci95_high']}) | {row['residual']} | {row['valid_outputs']} / {row['cases']} |"
        )
    report += [
        "",
        "## Interpretation guardrail",
        "",
        "These are synthetic benchmark results. They are not evidence of safety on clinical data unless an external validation campaign and human adjudication are completed.",
    ]
    report_path = output / "MANUSCRIPT_REPORT.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    generated.append(report_path)

    appendix = [
        "# Reproducibility appendix",
        "",
        f"- Software version: `{__version__}`",
        f"- Generated at: `{_now()}`",
        f"- Workspace: `{workspace_path if disclose_paths else '<redacted>'}`",
        "- All tables have machine-readable CSV companions.",
        "- Input and output SHA-256 digests are recorded in `publication_manifest.json`.",
    ]
    appendix_path = output / "REPRODUCIBILITY_APPENDIX.md"
    appendix_path.write_text("\n".join(appendix) + "\n", encoding="utf-8")
    generated.append(appendix_path)

    try:
        import matplotlib.pyplot as plt

        labels = [row["pipeline"] for row in overall]
        values = [float(row["removal_rate"]) for row in overall]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(labels, values)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Identifier removal rate")
        ax.set_title("Overall synthetic identifier removal")
        fig.tight_layout()
        figure = output / "figures" / "overall_removal_rate.png"
        figure.parent.mkdir(parents=True, exist_ok=True)
        restrict_directory(figure.parent)
        fig.savefig(figure, dpi=200, bbox_inches="tight")
        plt.close(fig)
        restrict_file(figure)
        generated.append(figure)
    except ImportError:
        pass

    manifest = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "software_version": __version__,
        "title": title,
        "synthetic_results": True,
        "paths_disclosed": disclose_paths,
        "inputs": [
            {
                "path": (
                    str(path.resolve())
                    if disclose_paths
                    else (
                        path.resolve().relative_to(workspace_path).as_posix()
                        if path.resolve().is_relative_to(workspace_path)
                        else path.name
                    )
                ),
                "sha256": _sha256(path),
            }
            for path in input_paths
            if path.is_file()
        ],
        "outputs": [
            {"path": str(path.relative_to(output)), "sha256": _sha256(path)}
            for path in generated
            if path.is_file()
        ],
        "review_summary": review_summary,
    }
    for generated_path in generated:
        restrict_file(generated_path)

    manifest_path = write_json(
        output / "publication_manifest.json", manifest, schema_name="publication-manifest"
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest
