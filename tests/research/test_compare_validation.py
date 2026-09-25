import json

import pandas as pd
import pytest

from open_equity_data.research.compare_validation import compare


def make_outputs(tmp_path, *, rsi_n=100):
    baselines = tmp_path / "baselines"
    tabpfn = tmp_path / "tabpfn"
    rsi = tmp_path / "rsi"
    for model in ("base_rate", "logistic", "hist_gradient_boosting", "tabpfn_3_5"):
        root = tabpfn if model == "tabpfn_3_5" else baselines
        path = root / model / "1d"
        path.mkdir(parents=True)
        (path / "summary.json").write_text(json.dumps({
            "n": 100, "roc_auc": 0.53, "log_loss": 0.69,
            "brier_score": 0.25, "mean_ic": 0.04,
            "ic_newey_west_t": 2.0, "d10_minus_d1_mean": 0.001,
            "d10_minus_d1_nw_t": 2.1,
        }))
        (path / "run_metadata.json").write_text(json.dumps({
            "train_rows": 5000, "n_estimators": 1,
        }))
    rsi.mkdir()
    pd.DataFrame([
        {"model": f"rsi14_{direction}", "horizon_days": 1, "n": rsi_n,
         "mean_ic": 0.01, "ic_newey_west_t": 1.0,
         "d10_minus_d1_mean": 0.002, "d10_minus_d1_nw_t": 1.2}
        for direction in ("reversal", "continuation")
    ]).to_csv(rsi / "validation_summary.csv", index=False)
    return baselines, tabpfn, rsi


def test_comparison_keeps_rsi_probability_metrics_empty(tmp_path):
    result = compare(1, *make_outputs(tmp_path))
    assert len(result) == 6
    assert result.loc[result["kind"] == "fixed rank score", "roc_auc"].isna().all()
    assert result.loc[result["model"] == "tabpfn_3_5", "n_estimators"].iloc[0] == 1


def test_comparison_rejects_different_validation_export(tmp_path):
    with pytest.raises(ValueError, match="row counts differ"):
        compare(1, *make_outputs(tmp_path, rsi_n=50))
