from __future__ import annotations

import json
from pathlib import Path


def create_plots(evaluation_json: str | Path, output_dir: str | Path) -> list[Path]:
    """Create publication-oriented PNG figures from an evaluation JSON file."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    payload = json.loads(Path(evaluation_json).read_text(encoding="utf-8"))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = payload.get("by_stratum", [])
    generated: list[Path] = []
    if not rows:
        return generated

    labels = [row["stratum"].replace("_", " ") for row in rows]
    rates = [row["removal_rate"] for row in rows]
    low = [row["removal_rate"] - row["removal_rate_ci95_low"] for row in rows]
    high = [row["removal_rate_ci95_high"] - row["removal_rate"] for row in rows]

    figure, axis = plt.subplots(figsize=(10, 6))
    axis.barh(labels, rates, xerr=[low, high], capsize=3)
    axis.set_xlim(0, 1.05)
    axis.set_xlabel("Identifier removal rate")
    axis.set_ylabel("Benchmark stratum")
    axis.set_title(f"De-identification performance: {payload['pipeline']}")
    figure.tight_layout()
    path = output / "removal_rate_by_stratum.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    generated.append(path)

    residuals = [row["residual"] for row in rows]
    figure, axis = plt.subplots(figsize=(10, 6))
    axis.barh(labels, residuals)
    axis.set_xlabel("Residual synthetic identifiers")
    axis.set_ylabel("Benchmark stratum")
    axis.set_title(f"Residual privacy leaks: {payload['pipeline']}")
    figure.tight_layout()
    path = output / "residuals_by_stratum.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    generated.append(path)
    return generated
