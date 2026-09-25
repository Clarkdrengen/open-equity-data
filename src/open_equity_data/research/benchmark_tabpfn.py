"""Validation-stage TabPFN-3.5 benchmark using the shared research outputs."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from open_equity_data.research.benchmark_dataset import HORIZONS
from open_equity_data.research.benchmark_models import (
    DEFAULT_DATASET_DIR,
    DEFAULT_OUTPUT_DIR,
    evaluate_and_persist,
    feature_matrix,
    load_parquet,
    prediction_frame,
    save_csv,
    save_json,
    target_vector,
    validate_model_frame,
)

MODEL_NAME = "tabpfn_3_5"


def validate_splits(train: pd.DataFrame, validation: pd.DataFrame) -> None:
    """Reject mislabeled exports and forward labels crossing split boundaries."""
    for frame, name, start, end in (
        (train, "train", "2011-01-01", "2022-12-31"),
        (validation, "validation", "2023-01-01", "2024-12-31"),
    ):
        validate_model_frame(frame)
        if frame.empty:
            raise ValueError(f"{name} dataset is empty")
        dates = pd.to_datetime(frame["date"])
        ends = pd.to_datetime(frame["target_end_date"])
        if dates.isna().any() or ends.isna().any():
            raise ValueError(f"{name} has missing dates")
        if (dates < pd.Timestamp(start)).any() or (dates > pd.Timestamp(end)).any():
            raise ValueError(f"{name} signal dates fall outside {start}..{end}")
        if (ends <= dates).any() or (ends > pd.Timestamp(end)).any():
            raise ValueError(f"{name} labels cross the split boundary or precede the signal")
    if len(np.unique(target_vector(train))) != 2:
        raise ValueError("TabPFN training sample must contain both target classes")


def fit_predict(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    device: str = "auto",
    batch_size: int = 1000,
) -> tuple[np.ndarray, dict]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    try:
        import torch
        from tabpfn import TabPFNClassifier
        from tabpfn.constants import ModelVersion
    except ImportError as exc:
        raise RuntimeError('Install the optional model dependency: pip install -e ".[tabpfn]"') from exc

    accelerator = torch.cuda.is_available() or (
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    )
    if device == "cpu" or (device == "auto" and not accelerator):
        if len(train) > 5000:
            raise RuntimeError(
                "TabPFN CPU training is limited to a practical 5,000-row pilot. "
                "Re-export datasets with --tabpfn-train-rows 5000, or run on an accelerator."
            )

    t0 = time.monotonic()
    model = TabPFNClassifier.create_default_for_version(
        ModelVersion.V3_5, device=device, random_state=20260924
    )
    model.fit(feature_matrix(train), target_vector(train))
    fit_seconds = time.monotonic() - t0

    classes = np.asarray(model.classes_)
    positive = np.flatnonzero(classes == 1)
    if len(positive) != 1:
        raise ValueError(f"TabPFN did not expose positive class 1: {classes}")

    x = feature_matrix(validation)
    chunks = []
    t1 = time.monotonic()
    for offset in range(0, len(x), batch_size):
        chunk = np.asarray(model.predict_proba(x[offset:offset + batch_size]))
        expected = min(batch_size, len(x) - offset)
        if chunk.shape != (expected, len(classes)):
            raise ValueError(f"Unexpected TabPFN probability shape: {chunk.shape}")
        chunks.append(chunk[:, positive[0]])
    probabilities = np.concatenate(chunks)
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("TabPFN returned invalid probabilities")
    return probabilities, {
        "model": MODEL_NAME,
        "model_version": "V3_5",
        "device": device,
        "batch_size": batch_size,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "train_positive_rate": float(target_vector(train).mean()),
        "fit_seconds": fit_seconds,
        "predict_seconds": time.monotonic() - t1,
    }


def run_horizon(
    horizon: int,
    dataset_dir: Path = DEFAULT_DATASET_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    device: str = "auto",
    batch_size: int = 1000,
) -> dict:
    if horizon not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")
    source = dataset_dir / f"{horizon}d"
    train = load_parquet(source / "train_tabpfn.parquet")
    validation = load_parquet(source / "validation.parquet")
    validate_splits(train, validation)
    probabilities, metadata = fit_predict(
        train, validation, device=device, batch_size=batch_size
    )
    predictions = prediction_frame(validation, probabilities, MODEL_NAME, horizon)
    summary = evaluate_and_persist(predictions, output_dir, MODEL_NAME, horizon)
    save_json(metadata, output_dir / MODEL_NAME / f"{horizon}d" / "run_metadata.json")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TabPFN-3.5 on validation only")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--horizon", type=int, choices=HORIZONS)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    horizons = (args.horizon,) if args.horizon else HORIZONS
    summaries = []
    for horizon in horizons:
        print(f"Running TabPFN-3.5, {horizon}d horizon", flush=True)
        summaries.append(run_horizon(
            horizon, args.dataset_dir, args.output_dir,
            device=args.device, batch_size=args.batch_size,
        ))
    result = pd.DataFrame(summaries)
    save_csv(result, args.output_dir / "tabpfn_validation_summary.csv")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
