from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluations", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("workflow_summary.csv"))
    args = parser.parse_args()
    rows = []
    for path in args.evaluations:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        rows.append(
            {
                "pipeline": payload["pipeline"],
                "cases": summary["cases"],
                "injections": summary["injections"],
                "removal_rate": summary["removal_rate"],
                "residual_injections": summary["residual_injections"],
                "auditor_residual_sensitivity": summary["auditor_residual_sensitivity"],
                "false_positive_control_rate": summary["false_positive_control_rate"],
                "basic_valid_outputs": summary["basic_valid_outputs"],
                "mean_runtime_seconds": summary["mean_runtime_seconds"],
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(args.output)


if __name__ == "__main__":
    main()
