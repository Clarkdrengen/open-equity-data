"""Pre-specified RSI(14) continuation and reversal validation diagnostics.

RSI ranks are scores, not calibrated probabilities. We therefore report
cross-sectional returns and IC, but not classification loss or calibration.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from open_equity_data.research.benchmark_dataset import HORIZONS
from open_equity_data.research.benchmark_models import (
    DEFAULT_DATASET_DIR, DEFAULT_OUTPUT_DIR, load_parquet, save_csv, save_json,
)
from open_equity_data.research.cross_sectional_metrics import (
    evaluate_cross_section, hac_lag, newey_west_mean_test,
)


def validate_validation(frame: pd.DataFrame) -> None:
    required = {
        "security_id", "date", "target_end_date", "target",
        "forward_relative_return", "rsi_14",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing RSI columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("Validation dataset is empty")
    dates = pd.to_datetime(frame["date"])
    ends = pd.to_datetime(frame["target_end_date"])
    boundary = pd.Timestamp("2024-12-31")
    if dates.isna().any() or ends.isna().any() or (
        (dates < pd.Timestamp("2023-01-01")) | (dates > boundary)
        | (ends <= dates) | (ends > boundary)
    ).any():
        raise ValueError("Validation dates or forward labels cross the 2023–2024 split")
    if frame.duplicated(["security_id", "date"]).any():
        raise ValueError("Duplicate security_id/date observations")
    rsi = frame["rsi_14"].to_numpy(dtype=float)
    returns = frame["forward_relative_return"].to_numpy(dtype=float)
    if not np.isfinite(rsi).all() or ((rsi < 0) | (rsi > 100)).any():
        raise ValueError("RSI(14) must be finite and lie in [0, 100]")
    if not np.isfinite(returns).all():
        raise ValueError("Forward returns must be finite")


def threshold_summary(frame: pd.DataFrame, horizon: int) -> tuple[dict, pd.DataFrame]:
    """Daily paired <30 versus >70 forward-return contrast, without tuning."""
    x = frame[["date", "rsi_14", "forward_relative_return"]].copy()
    x["date"] = pd.to_datetime(x["date"])
    x["bucket"] = np.select(
        [x["rsi_14"] < 30, x["rsi_14"] > 70],
        ["below_30", "above_70"], default="neutral",
    )
    daily = x.groupby(["date", "bucket"], observed=True).agg(
        mean_return=("forward_relative_return", "mean"),
        n=("forward_relative_return", "size"),
    ).reset_index()
    wide = daily.pivot(index="date", columns="bucket", values="mean_return")
    if "below_30" in wide and "above_70" in wide:
        paired = (wide["below_30"] - wide["above_70"]).dropna()
    else:
        paired = pd.Series(dtype=float)
    t, _ = newey_west_mean_test(paired, maxlags=hac_lag(horizon))
    count = x["bucket"].value_counts()
    summary = {
        "below_30_rows": int(count.get("below_30", 0)),
        "above_70_rows": int(count.get("above_70", 0)),
        "paired_dates": int(len(paired)),
        "below_30_minus_above_70_mean": float(paired.mean()) if len(paired) else np.nan,
        "below_30_minus_above_70_nw_t": float(t),
    }
    return summary, daily


def evaluate_horizon(frame: pd.DataFrame, horizon: int, output_dir: Path) -> pd.DataFrame:
    validate_validation(frame)
    events, daily_events = threshold_summary(frame, horizon)
    save_csv(daily_events, output_dir / f"{horizon}d" / "threshold_daily.csv")
    save_json(events, output_dir / f"{horizon}d" / "threshold_summary.json")

    rows = []
    for hypothesis, score in (
        ("reversal", 1 - frame["rsi_14"] / 100),
        ("continuation", frame["rsi_14"] / 100),
    ):
        # This column is a [0,1] rank score for the shared cross-sectional
        # evaluator; it must not be interpreted as a predicted probability.
        signal = frame[["security_id", "date", "target", "forward_relative_return"]].copy()
        signal["predicted_probability"] = score.to_numpy(dtype=float)
        result = evaluate_cross_section(signal, horizon=horizon)
        location = output_dir / f"{horizon}d" / hypothesis
        save_csv(result["daily_rank_ic"], location / "daily_rank_ic.csv")
        save_csv(result["daily_decile_returns"], location / "daily_decile_returns.csv")
        save_csv(result["decile_statistics"], location / "decile_statistics.csv")
        spread = result["decile_statistics"].set_index("decile").loc["D10-D1"]
        rows.append({
            "model": f"rsi14_{hypothesis}",
            "horizon_days": horizon,
            "sample": "validation",
            "n": len(frame),
            "mean_ic": result["rank_ic_summary"]["mean_ic"],
            "ic_newey_west_t": result["rank_ic_summary"]["newey_west_t"],
            "d10_minus_d1_mean": spread["mean_period_return"],
            "d10_minus_d1_nw_t": spread["newey_west_t"],
            "threshold_paired_dates": events["paired_dates"],
            "below_30_minus_above_70_mean": events["below_30_minus_above_70_mean"],
            "below_30_minus_above_70_nw_t": events["below_30_minus_above_70_nw_t"],
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fixed RSI(14) hypotheses on validation")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "rsi14")
    parser.add_argument("--horizon", type=int, choices=HORIZONS)
    args = parser.parse_args()
    summaries = []
    for horizon in (args.horizon,) if args.horizon else HORIZONS:
        frame = load_parquet(args.dataset_dir / f"{horizon}d" / "validation.parquet")
        summaries.append(evaluate_horizon(frame, horizon, args.output_dir))
    output = pd.concat(summaries, ignore_index=True)
    save_csv(output, args.output_dir / "validation_summary.csv")
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
