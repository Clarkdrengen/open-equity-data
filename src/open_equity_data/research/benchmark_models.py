"""
Baseline models for the multi-horizon technical return benchmark.

Development-stage rule:
    train on the training sample
    evaluate on validation
    do not expose the 2025+ test set

Models:
    - training-prior base rate
    - standardized logistic regression
    - histogram gradient boosting

For every model/horizon combination, validation predictions are persisted
and then passed through the common predictive and cross-sectional research
framework.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_equity_data.research.benchmark_dataset import (
    FEATURES,
    HORIZONS,
)
from open_equity_data.research.cross_sectional_metrics import (
    assign_daily_deciles,
    evaluate_cross_section,
    staggered_payoff_indices,
)
from open_equity_data.research.predictive_metrics import (
    calibration_table,
    evaluate_predictions,
    expected_calibration_error,
)


DEFAULT_DATASET_DIR = Path(
    "artifacts/research/benchmark_v1/datasets"
)

DEFAULT_OUTPUT_DIR = Path(
    "artifacts/research/benchmark_v1/baselines"
)

MODELS = (
    "base_rate",
    "logistic",
    "hist_gradient_boosting",
)

RANDOM_STATE = 20260924


def load_parquet(
    path: Path,
) -> pd.DataFrame:
    """
    Load through DuckDB so pyarrow is not required.
    """

    if not path.exists():
        raise FileNotFoundError(path)

    con = duckdb.connect()

    try:
        return con.execute(
            """
            SELECT *
            FROM read_parquet(?)
            """,
            [str(path)],
        ).df()

    finally:
        con.close()


def write_parquet(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    """
    Persist a pandas DataFrame as compressed Parquet through DuckDB.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    con = duckdb.connect()

    try:
        con.register(
            "output_frame",
            frame,
        )

        con.execute(
            f"""
            COPY output_frame
            TO '{str(path.resolve()).replace("'", "''")}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
            """
        )

    finally:
        con.close()


def validate_model_frame(
    frame: pd.DataFrame,
) -> None:
    required = {
        "security_id",
        "date",
        "ticker",
        "target",
        "forward_relative_return",
        "target_end_date",
        *FEATURES,
    }

    missing = required - set(
        frame.columns
    )

    if missing:
        raise ValueError(
            "Missing model columns: "
            + ", ".join(sorted(missing))
        )

    matrix = frame.loc[
        :,
        FEATURES,
    ].to_numpy(
        dtype=float,
    )

    if not np.isfinite(matrix).all():
        bad = np.size(matrix) - np.isfinite(
            matrix
        ).sum()

        raise ValueError(
            f"Feature matrix contains "
            f"{bad:,} non-finite values"
        )

    target = frame[
        "target"
    ].to_numpy()

    if not set(
        np.unique(target)
    ).issubset({0, 1}):
        raise ValueError(
            "Target contains values other than 0/1"
        )


def feature_matrix(
    frame: pd.DataFrame,
) -> np.ndarray:
    return frame.loc[
        :,
        FEATURES,
    ].to_numpy(
        dtype=np.float64,
        copy=True,
    )


def target_vector(
    frame: pd.DataFrame,
) -> np.ndarray:
    return frame[
        "target"
    ].to_numpy(
        dtype=np.int64,
        copy=True,
    )


def make_logistic_model() -> Pipeline:
    """
    Conventional linear probabilistic benchmark.

    No class weighting is used because preserving probability calibration
    and the naturally changing class prior is part of the experiment.
    """

    return Pipeline(
        steps=[
            (
                "scale",
                StandardScaler(),
            ),
            (
                "model",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=500,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def make_gradient_boosting_model(
) -> HistGradientBoostingClassifier:
    """
    Nonlinear tree benchmark from scikit-learn.

    HistGradientBoosting scales much better to the one-million-row training
    samples than classic GradientBoostingClassifier.
    """

    return HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=200,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.10,
        n_iter_no_change=20,
        random_state=RANDOM_STATE,
    )


def fit_predict_model(
    model_name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> tuple[np.ndarray, dict]:
    """
    Fit a model and return validation probabilities plus run metadata.
    """

    y_train = target_vector(
        train
    )

    metadata: dict = {
        "model": model_name,
        "train_rows": int(
            len(train)
        ),
        "validation_rows": int(
            len(validation)
        ),
        "train_positive_rate": float(
            y_train.mean()
        ),
    }

    t0 = time.time()

    if model_name == "base_rate":
        train_prior = float(
            y_train.mean()
        )

        probabilities = np.full(
            len(validation),
            train_prior,
            dtype=float,
        )

        metadata[
            "fit_seconds"
        ] = 0.0

    elif model_name == "logistic":
        model = make_logistic_model()

        model.fit(
            feature_matrix(train),
            y_train,
        )

        metadata[
            "fit_seconds"
        ] = time.time() - t0

        t1 = time.time()

        probabilities = model.predict_proba(
            feature_matrix(validation)
        )[:, 1]

        metadata[
            "predict_seconds"
        ] = time.time() - t1

        logistic = model.named_steps[
            "model"
        ]

        metadata[
            "iterations"
        ] = [
            int(x)
            for x in logistic.n_iter_
        ]

    elif model_name == "hist_gradient_boosting":
        model = (
            make_gradient_boosting_model()
        )

        model.fit(
            feature_matrix(train),
            y_train,
        )

        metadata[
            "fit_seconds"
        ] = time.time() - t0

        t1 = time.time()

        probabilities = model.predict_proba(
            feature_matrix(validation)
        )[:, 1]

        metadata[
            "predict_seconds"
        ] = time.time() - t1

        metadata[
            "iterations"
        ] = int(
            model.n_iter_
        )

    else:
        raise ValueError(
            f"Unknown model: {model_name}"
        )

    if "predict_seconds" not in metadata:
        metadata[
            "predict_seconds"
        ] = 0.0

    metadata[
        "mean_validation_prediction"
    ] = float(
        probabilities.mean()
    )

    return probabilities, metadata


def prediction_frame(
    validation: pd.DataFrame,
    probabilities: np.ndarray,
    model_name: str,
    horizon: int,
) -> pd.DataFrame:
    if len(validation) != len(
        probabilities
    ):
        raise ValueError(
            "Validation rows and probabilities "
            "have different lengths"
        )

    return pd.DataFrame(
        {
            "security_id":
                validation[
                    "security_id"
                ].to_numpy(),

            "date":
                pd.to_datetime(
                    validation[
                        "date"
                    ]
                ),

            "ticker":
                validation[
                    "ticker"
                ].to_numpy(),

            "target_end_date":
                pd.to_datetime(
                    validation[
                        "target_end_date"
                    ]
                ),

            "model":
                model_name,

            "horizon":
                horizon,

            "sample":
                "validation",

            "target":
                validation[
                    "target"
                ].astype(int).to_numpy(),

            "forward_relative_return":
                validation[
                    "forward_relative_return"
                ].astype(float).to_numpy(),

            "predicted_probability":
                np.asarray(
                    probabilities,
                    dtype=float,
                ),
        }
    )


def save_json(
    value: dict,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=True,
        )
        + "\n"
    )


def save_csv(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.to_csv(
        path,
        index=False,
    )


def evaluate_and_persist(
    predictions: pd.DataFrame,
    output_dir: Path,
    model_name: str,
    horizon: int,
) -> dict:
    """
    Persist predictions and all generic validation research outputs.
    """

    run_dir = (
        output_dir
        / model_name
        / f"{horizon}d"
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_parquet(
        predictions,
        run_dir
        / "validation_predictions.parquet",
    )

    predictive = evaluate_predictions(
        y_true=predictions[
            "target"
        ].to_numpy(),
        y_prob=predictions[
            "predicted_probability"
        ].to_numpy(),
    )

    calibration = calibration_table(
        y_true=predictions[
            "target"
        ].to_numpy(),
        y_prob=predictions[
            "predicted_probability"
        ].to_numpy(),
        n_bins=10,
    )

    ece = (
        expected_calibration_error(
            calibration
        )
    )

    predictive_summary = (
        predictive.as_dict()
    )

    predictive_summary[
        "expected_calibration_error"
    ] = float(ece)

    save_json(
        predictive_summary,
        run_dir
        / "predictive_metrics.json",
    )

    save_csv(
        calibration,
        run_dir
        / "calibration.csv",
    )

    cross = evaluate_cross_section(
        predictions,
        horizon=horizon,
    )

    save_csv(
        cross[
            "decile_statistics"
        ],
        run_dir
        / "decile_statistics.csv",
    )

    save_csv(
        cross[
            "daily_decile_returns"
        ],
        run_dir
        / "daily_decile_returns.csv",
    )

    save_csv(
        cross[
            "daily_rank_ic"
        ],
        run_dir
        / "daily_rank_ic.csv",
    )

    save_json(
        cross[
            "rank_ic_summary"
        ],
        run_dir
        / "rank_ic_summary.json",
    )

    save_json(
        cross[
            "monotonicity"
        ],
        run_dir
        / "monotonicity.json",
    )

    save_json(
        cross[
            "long_short_decomposition"
        ],
        run_dir
        / "long_short_decomposition.json",
    )

    ranked = assign_daily_deciles(
        predictions
    )

    payoff = staggered_payoff_indices(
        ranked,
        horizon=horizon,
    )

    save_csv(
        payoff,
        run_dir
        / "payoff_indices.csv",
    )

    decile_stats = cross[
        "decile_statistics"
    ]

    spread_row = decile_stats.loc[
        decile_stats["decile"]
        == "D10-D1"
    ]

    spread = (
        spread_row.iloc[0]
        if not spread_row.empty
        else None
    )

    summary = {
        "model":
            model_name,

        "horizon_days":
            horizon,

        "sample":
            "validation",

        "n":
            predictive_summary[
                "n"
            ],

        "positive_rate":
            predictive_summary[
                "positive_rate"
            ],

        "mean_prediction":
            predictive_summary[
                "mean_prediction"
            ],

        "roc_auc":
            predictive_summary[
                "roc_auc"
            ],

        "log_loss":
            predictive_summary[
                "log_loss"
            ],

        "brier_score":
            predictive_summary[
                "brier_score"
            ],

        "accuracy":
            predictive_summary[
                "accuracy"
            ],

        "ece":
            predictive_summary[
                "expected_calibration_error"
            ],

        "mean_ic":
            cross[
                "rank_ic_summary"
            ][
                "mean_ic"
            ],

        "icir":
            cross[
                "rank_ic_summary"
            ][
                "icir"
            ],

        "ic_newey_west_t":
            cross[
                "rank_ic_summary"
            ][
                "newey_west_t"
            ],

        "ic_hit_rate":
            cross[
                "rank_ic_summary"
            ][
                "hit_rate"
            ],

        "decile_spearman":
            cross[
                "monotonicity"
            ][
                "spearman_decile_return"
            ],

        "strictly_monotone":
            cross[
                "monotonicity"
            ][
                "strictly_monotone"
            ],

        "d10_minus_d1_mean":
            (
                float(
                    spread[
                        "mean_period_return"
                    ]
                )
                if spread is not None
                else np.nan
            ),

        "d10_minus_d1_ir":
            (
                float(
                    spread[
                        "information_ratio"
                    ]
                )
                if spread is not None
                else np.nan
            ),

        "d10_minus_d1_nw_t":
            (
                float(
                    spread[
                        "newey_west_t"
                    ]
                )
                if spread is not None
                else np.nan
            ),
    }

    save_json(
        summary,
        run_dir
        / "summary.json",
    )

    return summary


def run_horizon(
    horizon: int,
    dataset_dir: Path,
    output_dir: Path,
) -> list[dict]:
    horizon_dir = (
        dataset_dir
        / f"{horizon}d"
    )

    train_path = (
        horizon_dir
        / "train_large.parquet"
    )

    validation_path = (
        horizon_dir
        / "validation.parquet"
    )

    horizon_start = time.time()

    print(
        f"\n=== {horizon}d horizon ===",
        flush=True,
    )

    print(
        "[1/4] Loading datasets...",
        flush=True,
    )

    t_load = time.time()

    train = load_parquet(
        train_path
    )

    validation = load_parquet(
        validation_path
    )

    print(
        f"      loaded in "
        f"{time.time() - t_load:.1f}s",
        flush=True,
    )

    print(
        "[2/4] Validating datasets...",
        flush=True,
    )

    t_validate = time.time()

    validate_model_frame(
        train
    )

    validate_model_frame(
        validation
    )

    print(
        f"      validated in "
        f"{time.time() - t_validate:.1f}s",
        flush=True,
    )

    print(
        f"      train={len(train):,} "
        f"validation={len(validation):,}",
        flush=True,
    )

    summaries = []

    for model_number, model_name in enumerate(
        MODELS,
        start=1,
    ):
        print(
            f"[3/4] Model {model_number}/{len(MODELS)}: "
            f"{model_name}",
            flush=True,
        )

        print(
            "      fitting/predicting...",
            flush=True,
        )

        t0 = time.time()

        probabilities, metadata = (
            fit_predict_model(
                model_name=model_name,
                train=train,
                validation=validation,
            )
        )

        predictions = prediction_frame(
            validation=validation,
            probabilities=probabilities,
            model_name=model_name,
            horizon=horizon,
        )

        print(
            f"      fit={metadata['fit_seconds']:.1f}s "
            f"predict={metadata['predict_seconds']:.1f}s",
            flush=True,
        )

        print(
            "      evaluating/persisting...",
            flush=True,
        )

        t_eval = time.time()

        summary = (
            evaluate_and_persist(
                predictions=predictions,
                output_dir=output_dir,
                model_name=model_name,
                horizon=horizon,
            )
        )

        metadata[
            "evaluation_seconds"
        ] = time.time() - t_eval

        metadata[
            "total_seconds"
        ] = time.time() - t0

        save_json(
            metadata,
            output_dir
            / model_name
            / f"{horizon}d"
            / "run_metadata.json",
        )

        summaries.append(
            summary
        )

        print(
            "      "
            f"AUC={summary['roc_auc']:.4f} "
            f"IC={summary['mean_ic']:.4f} "
            f"ICIR={summary['icir']:.4f} "
            f"D10-D1="
            f"{summary['d10_minus_d1_mean']:.5f} "
            f"NW t="
            f"{summary['d10_minus_d1_nw_t']:.2f}",
            flush=True,
        )

        print(
            f"      evaluation="
            f"{metadata['evaluation_seconds']:.1f}s "
            f"model total="
            f"{metadata['total_seconds']:.1f}s "
            f"horizon elapsed="
            f"{time.time() - horizon_start:.1f}s",
            flush=True,
        )

    print(
        f"[4/4] {horizon}d horizon complete in "
        f"{time.time() - horizon_start:.1f}s",
        flush=True,
    )

    del train
    del validation

    return summaries


def run_all(
    dataset_dir: Path = DEFAULT_DATASET_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_summaries: list[dict] = []

    for horizon in HORIZONS:
        all_summaries.extend(
            run_horizon(
                horizon=horizon,
                dataset_dir=dataset_dir,
                output_dir=output_dir,
            )
        )

    summary = pd.DataFrame(
        all_summaries
    ).sort_values(
        [
            "horizon_days",
            "model",
        ]
    )

    save_csv(
        summary,
        output_dir
        / "validation_summary.csv",
    )

    print(
        "\nVALIDATION SUMMARY\n",
        flush=True,
    )

    columns = [
        "model",
        "horizon_days",
        "roc_auc",
        "log_loss",
        "brier_score",
        "mean_ic",
        "icir",
        "d10_minus_d1_mean",
        "d10_minus_d1_ir",
        "d10_minus_d1_nw_t",
    ]

    print(
        summary[
            columns
        ].to_string(
            index=False
        )
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run conventional validation-stage "
            "benchmark models."
        )
    )

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--horizon",
        type=int,
        choices=HORIZONS,
        default=None,
        help=(
            "Run one horizon only. "
            "Default runs all horizons."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.horizon is None:
        run_all(
            dataset_dir=args.dataset_dir,
            output_dir=args.output_dir,
        )

    else:
        summaries = run_horizon(
            horizon=args.horizon,
            dataset_dir=args.dataset_dir,
            output_dir=args.output_dir,
        )

        print(
            pd.DataFrame(
                summaries
            ).to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
