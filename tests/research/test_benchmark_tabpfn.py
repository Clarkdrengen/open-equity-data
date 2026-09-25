import sys
import types

import numpy as np
import pandas as pd
import pytest

from open_equity_data.research.benchmark_tabpfn import fit_predict, validate_splits
from tests.research.test_benchmark_models import make_model_frame


def split_frames():
    train = make_model_frame(40)
    validation = make_model_frame(21)
    train["date"] = pd.date_range("2021-01-01", periods=len(train))
    train["target_end_date"] = train["date"] + pd.Timedelta(days=1)
    validation["date"] = pd.date_range("2023-01-01", periods=len(validation))
    validation["target_end_date"] = validation["date"] + pd.Timedelta(days=1)
    return train, validation


def test_rejects_train_labels_leaking_into_validation():
    train, validation = split_frames()
    train.loc[0, "target_end_date"] = pd.Timestamp("2023-01-03")
    with pytest.raises(ValueError, match="split boundary"):
        validate_splits(train, validation)


def test_rejects_validation_labels_leaking_into_test():
    train, validation = split_frames()
    validation.loc[0, "target_end_date"] = pd.Timestamp("2025-01-02")
    with pytest.raises(ValueError, match="split boundary"):
        validate_splits(train, validation)


def test_tabpfn_batches_and_selects_positive_class(monkeypatch):
    train, validation = split_frames()
    validate_splits(train, validation)
    calls = []

    class FakeModel:
        classes_ = np.array([1, 0])

        def fit(self, x, y):
            assert len(x) == len(train)

        def predict_proba(self, x):
            calls.append(len(x))
            return np.tile([0.7, 0.3], (len(x), 1))

    class FakeClassifier:
        @staticmethod
        def create_default_for_version(version, **kwargs):
            assert version == "V3_5"
            return FakeModel()

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
    ))
    monkeypatch.setitem(sys.modules, "tabpfn", types.SimpleNamespace(TabPFNClassifier=FakeClassifier))
    monkeypatch.setitem(sys.modules, "tabpfn.constants", types.SimpleNamespace(
        ModelVersion=types.SimpleNamespace(V3_5="V3_5")
    ))
    probabilities, metadata = fit_predict(train, validation, batch_size=8)
    assert calls == [8, 8, 5]
    assert np.allclose(probabilities, 0.7)
    assert metadata["model_version"] == "V3_5"


def test_mps_accelerator_failure_suggests_separate_cpu_pilot(monkeypatch):
    train, validation = split_frames()

    class FakeAcceleratorError(Exception):
        pass

    class FakeModel:
        classes_ = np.array([0, 1])

        def fit(self, x, y):
            pass

        def predict_proba(self, x):
            raise FakeAcceleratorError("device failed")

    class FakeClassifier:
        @staticmethod
        def create_default_for_version(version, **kwargs):
            return FakeModel()

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        AcceleratorError=FakeAcceleratorError,
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True)),
    ))
    monkeypatch.setitem(sys.modules, "tabpfn", types.SimpleNamespace(TabPFNClassifier=FakeClassifier))
    monkeypatch.setitem(sys.modules, "tabpfn.constants", types.SimpleNamespace(
        ModelVersion=types.SimpleNamespace(V3_5="V3_5")
    ))
    with pytest.raises(RuntimeError, match="CPU smoke test"):
        fit_predict(train, validation, device="auto", batch_size=8)
