import numpy as np

from open_equity_data.research.predictive_metrics import (
    calibration_table,
    evaluate_predictions,
    expected_calibration_error,
)


def test_perfect_classifier():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.01, 0.05, 0.95, 0.99])

    result = evaluate_predictions(
        y,
        p,
    )

    assert result.roc_auc == 1.0
    assert result.accuracy == 1.0
    assert result.log_loss < 0.1
    assert result.brier_score < 0.01


def test_uninformative_classifier():
    y = np.array(
        [0, 1, 0, 1, 0, 1]
    )

    p = np.full(
        len(y),
        0.5,
    )

    result = evaluate_predictions(
        y,
        p,
    )

    assert result.roc_auc == 0.5
    assert np.isclose(
        result.brier_score,
        0.25,
    )


def test_calibration_table_counts():
    y = np.array(
        [0, 0, 0, 1, 1, 1, 1, 1]
    )

    p = np.array(
        [
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
        ]
    )

    table = calibration_table(
        y,
        p,
        n_bins=4,
    )

    assert table["n"].sum() == len(y)
    assert len(table) == 4


def test_expected_calibration_error_nonnegative():
    y = np.array(
        [0, 0, 1, 1]
    )

    p = np.array(
        [0.1, 0.4, 0.6, 0.9]
    )

    table = calibration_table(
        y,
        p,
        n_bins=2,
    )

    ece = expected_calibration_error(
        table
    )

    assert ece >= 0.0
