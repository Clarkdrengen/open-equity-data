"""
Predictive classification metrics for benchmark v1.

These metrics evaluate probabilistic prediction quality only. They do not
measure whether a model produces an economically useful cross-sectional signal.
That is handled separately in cross_sectional_metrics.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


@dataclass(frozen=True)
class PredictiveMetrics:
    n: int
    positive_rate: float
    mean_prediction: float
    roc_auc: float
    log_loss: float
    brier_score: float
    accuracy: float
    base_rate_accuracy: float
    base_rate_log_loss: float
    base_rate_brier_score: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "positive_rate": self.positive_rate,
            "mean_prediction": self.mean_prediction,
            "roc_auc": self.roc_auc,
            "log_loss": self.log_loss,
            "brier_score": self.brier_score,
            "accuracy": self.accuracy,
            "base_rate_accuracy": self.base_rate_accuracy,
            "base_rate_log_loss": self.base_rate_log_loss,
            "base_rate_brier_score": self.base_rate_brier_score,
        }


def validate_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob, dtype=float)

    if y_true.ndim != 1 or y_prob.ndim != 1:
        raise ValueError("y_true and y_prob must be one-dimensional")

    if len(y_true) != len(y_prob):
        raise ValueError("y_true and y_prob must have equal length")

    if len(y_true) == 0:
        raise ValueError("prediction arrays are empty")

    if np.isnan(y_true).any():
        raise ValueError("y_true contains NaN")

    if np.isnan(y_prob).any():
        raise ValueError("y_prob contains NaN")

    unique = set(np.unique(y_true))

    if not unique.issubset({0, 1}):
        raise ValueError(
            f"y_true must contain only 0/1 values; got {sorted(unique)}"
        )

    if np.any((y_prob < 0.0) | (y_prob > 1.0)):
        raise ValueError("predicted probabilities must lie in [0, 1]")

    return y_true.astype(int), y_prob


def evaluate_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> PredictiveMetrics:
    """
    Compute classifier metrics against an unconditional validation-set
    base-rate predictor.

    The base-rate benchmark predicts the observed positive fraction for every
    observation. It is diagnostic rather than a deployable out-of-sample model;
    later model runs may additionally supply a train-derived prior benchmark.
    """

    y_true, y_prob = validate_predictions(
        y_true,
        y_prob,
    )

    n = len(y_true)
    positive_rate = float(np.mean(y_true))

    eps = np.finfo(float).eps

    clipped_prob = np.clip(
        y_prob,
        eps,
        1.0 - eps,
    )

    base_prob = np.full(
        n,
        np.clip(
            positive_rate,
            eps,
            1.0 - eps,
        ),
    )

    y_pred = (
        clipped_prob >= threshold
    ).astype(int)

    base_class = int(
        positive_rate >= threshold
    )

    base_pred = np.full(
        n,
        base_class,
        dtype=int,
    )

    if len(np.unique(y_true)) < 2:
        auc = np.nan
    else:
        auc = float(
            roc_auc_score(
                y_true,
                clipped_prob,
            )
        )

    return PredictiveMetrics(
        n=n,
        positive_rate=positive_rate,
        mean_prediction=float(
            np.mean(clipped_prob)
        ),
        roc_auc=auc,
        log_loss=float(
            log_loss(
                y_true,
                clipped_prob,
                labels=[0, 1],
            )
        ),
        brier_score=float(
            brier_score_loss(
                y_true,
                clipped_prob,
            )
        ),
        accuracy=float(
            accuracy_score(
                y_true,
                y_pred,
            )
        ),
        base_rate_accuracy=float(
            accuracy_score(
                y_true,
                base_pred,
            )
        ),
        base_rate_log_loss=float(
            log_loss(
                y_true,
                base_prob,
                labels=[0, 1],
            )
        ),
        base_rate_brier_score=float(
            brier_score_loss(
                y_true,
                base_prob,
            )
        ),
    )


def calibration_table(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> pd.DataFrame:
    """
    Equal-frequency calibration table.

    Bins are assigned from predicted probability ranks rather than fixed
    probability intervals so each bin has useful sample size even if model
    predictions are tightly concentrated around the unconditional base rate.
    """

    y_true, y_prob = validate_predictions(
        y_true,
        y_prob,
    )

    if n_bins < 2:
        raise ValueError("n_bins must be at least 2")

    frame = pd.DataFrame(
        {
            "target": y_true,
            "predicted_probability": y_prob,
        }
    )

    rank = frame[
        "predicted_probability"
    ].rank(
        method="first",
        pct=True,
    )

    frame["calibration_bin"] = np.minimum(
        np.ceil(rank * n_bins).astype(int),
        n_bins,
    )

    result = (
        frame
        .groupby(
            "calibration_bin",
            observed=True,
        )
        .agg(
            n=("target", "size"),
            mean_prediction=(
                "predicted_probability",
                "mean",
            ),
            observed_rate=(
                "target",
                "mean",
            ),
        )
        .reset_index()
    )

    result["calibration_error"] = (
        result["mean_prediction"]
        - result["observed_rate"]
    )

    return result


def expected_calibration_error(
    calibration: pd.DataFrame,
) -> float:
    """
    Weighted absolute calibration error across bins.
    """

    required = {
        "n",
        "mean_prediction",
        "observed_rate",
    }

    missing = required - set(
        calibration.columns
    )

    if missing:
        raise ValueError(
            "calibration table missing: "
            + ", ".join(sorted(missing))
        )

    total = calibration["n"].sum()

    if total == 0:
        return np.nan

    return float(
        (
            calibration["n"]
            / total
            * (
                calibration[
                    "mean_prediction"
                ]
                - calibration[
                    "observed_rate"
                ]
            ).abs()
        ).sum()
    )
