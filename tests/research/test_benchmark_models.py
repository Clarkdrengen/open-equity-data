import numpy as np
import pandas as pd

from open_equity_data.research.benchmark_dataset import (
    FEATURES,
)
from open_equity_data.research.benchmark_models import (
    fit_predict_model,
    prediction_frame,
    validate_model_frame,
)


def make_model_frame(
    n: int = 200,
) -> pd.DataFrame:
    rng = np.random.default_rng(
        12345
    )

    data = {
        "security_id":
            np.arange(n),

        "date":
            pd.date_range(
                "2024-01-01",
                periods=n,
            ),

        "ticker":
            [f"T{i}" for i in range(n)],

        "target_end_date":
            pd.date_range(
                "2024-01-02",
                periods=n,
            ),
    }

    for i, feature in enumerate(
        FEATURES
    ):
        data[feature] = (
            rng.normal(
                loc=0.0,
                scale=1.0,
                size=n,
            )
            + i * 0.001
        )

    signal = (
        data[FEATURES[0]]
        + 0.5 * data[FEATURES[1]]
    )

    target = (
        signal > np.median(signal)
    ).astype(int)

    data["target"] = target

    data[
        "forward_relative_return"
    ] = (
        0.01
        * signal
    )

    return pd.DataFrame(data)


def test_validate_model_frame():
    frame = make_model_frame()

    validate_model_frame(
        frame
    )


def test_base_rate_uses_train_prior():
    train = make_model_frame(
        200
    )

    validation = make_model_frame(
        50
    )

    train.loc[
        :,
        "target",
    ] = 0

    train.loc[
        train.index[:50],
        "target",
    ] = 1

    probabilities, metadata = (
        fit_predict_model(
            model_name="base_rate",
            train=train,
            validation=validation,
        )
    )

    assert np.allclose(
        probabilities,
        0.25,
    )

    assert np.isclose(
        metadata[
            "train_positive_rate"
        ],
        0.25,
    )


def test_logistic_probabilities_are_valid():
    train = make_model_frame(
        300
    )

    validation = make_model_frame(
        100
    )

    probabilities, _ = (
        fit_predict_model(
            model_name="logistic",
            train=train,
            validation=validation,
        )
    )

    assert len(
        probabilities
    ) == len(validation)

    assert np.all(
        probabilities >= 0.0
    )

    assert np.all(
        probabilities <= 1.0
    )


def test_gradient_boosting_probabilities_are_valid():
    train = make_model_frame(
        300
    )

    validation = make_model_frame(
        100
    )

    probabilities, _ = (
        fit_predict_model(
            model_name=
                "hist_gradient_boosting",
            train=train,
            validation=validation,
        )
    )

    assert len(
        probabilities
    ) == len(validation)

    assert np.all(
        probabilities >= 0.0
    )

    assert np.all(
        probabilities <= 1.0
    )


def test_prediction_frame_metadata():
    validation = make_model_frame(
        20
    )

    p = np.full(
        len(validation),
        0.5,
    )

    result = prediction_frame(
        validation=validation,
        probabilities=p,
        model_name="example",
        horizon=5,
    )

    assert (
        result["model"]
        == "example"
    ).all()

    assert (
        result["horizon"]
        == 5
    ).all()

    assert (
        result["sample"]
        == "validation"
    ).all()

    assert (
        "target_end_date"
        in result.columns
    )
