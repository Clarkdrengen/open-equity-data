"""Side-by-side validation diagnostics for fitted models and RSI scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from open_equity_data.research.benchmark_dataset import HORIZONS
from open_equity_data.research.benchmark_models import DEFAULT_OUTPUT_DIR, MODELS, save_csv


def compare(
    horizon: int,
    baseline_dir: Path = DEFAULT_OUTPUT_DIR,
    tabpfn_dir: Path = Path("artifacts/research/benchmark_v1/tabpfn_mps_pilot"),
    rsi_dir: Path = DEFAULT_OUTPUT_DIR / "rsi14",
) -> pd.DataFrame:
    if horizon not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")
    rows = []
    for model in (*MODELS, "tabpfn_3_5"):
        root = tabpfn_dir if model == "tabpfn_3_5" else baseline_dir
        path = root / model / f"{horizon}d" / "summary.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}; run the {model} {horizon}d validation benchmark first"
            )
        summary = json.loads(path.read_text())
        metadata_path = path.with_name("run_metadata.json")
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        rows.append({
            "model": model,
            "kind": "fitted classifier" if model != "base_rate" else "base rate",
            "n": summary["n"],
            "train_rows": metadata.get("train_rows"),
            "n_estimators": metadata.get("n_estimators"),
            "roc_auc": summary["roc_auc"],
            "log_loss": summary["log_loss"],
            "brier_score": summary["brier_score"],
            "mean_ic": summary["mean_ic"],
            "ic_newey_west_t": summary["ic_newey_west_t"],
            "d10_minus_d1_mean": summary["d10_minus_d1_mean"],
            "d10_minus_d1_nw_t": summary["d10_minus_d1_nw_t"],
        })
    rsi_path = rsi_dir / "validation_summary.csv"
    if not rsi_path.exists():
        raise FileNotFoundError(f"Missing {rsi_path}; run benchmark_rsi first")
    rsi = pd.read_csv(rsi_path)
    rsi = rsi.loc[rsi["horizon_days"] == horizon]
    if len(rsi) != 2:
        raise ValueError(f"Expected both RSI directions for {horizon}d")
    for _, row in rsi.iterrows():
        rows.append({
            "model": row["model"], "kind": "fixed rank score", "n": row["n"],
            "mean_ic": row["mean_ic"],
            "ic_newey_west_t": row["ic_newey_west_t"],
            "d10_minus_d1_mean": row["d10_minus_d1_mean"],
            "d10_minus_d1_nw_t": row["d10_minus_d1_nw_t"],
        })
    result = pd.DataFrame(rows)
    if result["n"].nunique() != 1:
        raise ValueError("Validation row counts differ; comparisons require the same export")
    result.insert(0, "horizon_days", horizon)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare validation diagnostics")
    parser.add_argument("--horizon", type=int, choices=HORIZONS, default=1)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--tabpfn-dir", type=Path,
        default=Path("artifacts/research/benchmark_v1/tabpfn_mps_pilot"),
    )
    parser.add_argument("--rsi-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "rsi14")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    comparison = compare(args.horizon, args.baseline_dir, args.tabpfn_dir, args.rsi_dir)
    output = args.output or DEFAULT_OUTPUT_DIR / f"validation_comparison_{args.horizon}d.csv"
    save_csv(comparison, output)
    print(comparison.to_string(index=False))
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
