import numpy as np
import pandas as pd
import pytest

from open_equity_data.research.benchmark_rsi import (
    evaluate_horizon, threshold_summary, validate_validation,
)


def make_frame():
    rows = []
    for date in pd.bdate_range("2023-01-02", periods=20):
        for security, rsi in enumerate(np.linspace(10, 90, 40)):
            relative_return = (50 - rsi) / 5000
            rows.append({
                "security_id": security, "date": date,
                "target_end_date": date + pd.Timedelta(days=1),
                "target": int(relative_return > 0),
                "forward_relative_return": relative_return, "rsi_14": rsi,
            })
    return pd.DataFrame(rows)


def test_reversal_and_continuation_have_opposite_rank_signs(tmp_path):
    summary = evaluate_horizon(make_frame(), 1, tmp_path).set_index("model")
    assert summary.loc["rsi14_reversal", "mean_ic"] > 0.99
    assert summary.loc["rsi14_continuation", "mean_ic"] < -0.99
    assert summary.loc["rsi14_reversal", "d10_minus_d1_mean"] > 0
    assert summary.loc["rsi14_continuation", "d10_minus_d1_mean"] < 0
    assert (tmp_path / "1d" / "threshold_summary.json").exists()


def test_thresholds_are_strict_and_pair_same_dates():
    frame = make_frame()
    summary, daily = threshold_summary(frame, 1)
    assert summary["paired_dates"] == 20
    assert summary["below_30_rows"] == 200
    assert summary["above_70_rows"] == 200
    assert summary["below_30_minus_above_70_mean"] > 0
    assert len(daily) == 60


def test_rejects_labels_that_cross_validation_boundary():
    frame = make_frame()
    frame.loc[0, "target_end_date"] = pd.Timestamp("2025-01-02")
    with pytest.raises(ValueError, match="split"):
        validate_validation(frame)
