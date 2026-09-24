import numpy as np
import pandas as pd

from open_equity_data.research.cross_sectional_metrics import (
    assign_daily_deciles,
    daily_decile_returns,
    decile_statistics,
    hac_lag,
    daily_rank_ic,
    summarize_rank_ic,
    evaluate_cross_section,
)


def make_perfect_rank_frame(
    n_dates: int = 20,
    n_stocks: int = 100,
) -> pd.DataFrame:
    rows = []

    for day in range(n_dates):
        date = pd.Timestamp(
            "2024-01-01"
        ) + pd.Timedelta(days=day)

        for security in range(
            n_stocks
        ):
            score = (
                security
                / (n_stocks - 1)
            )

            realized = (
                -0.05
                + 0.10 * score
            )

            rows.append(
                {
                    "security_id":
                        security,

                    "date":
                        date,

                    "predicted_probability":
                        score,

                    "forward_relative_return":
                        realized,

                    "target":
                        int(realized > 0),
                }
            )

    return pd.DataFrame(rows)


def test_hac_lags():
    assert hac_lag(1) == 0
    assert hac_lag(5) == 4
    assert hac_lag(10) == 9
    assert hac_lag(20) == 19
    assert hac_lag(60) == 59


def test_daily_deciles():
    frame = make_perfect_rank_frame(
        n_dates=2
    )

    ranked = assign_daily_deciles(
        frame
    )

    counts = (
        ranked
        .groupby(
            ["date", "decile"]
        )
        .size()
    )

    assert counts.min() == 10
    assert counts.max() == 10
    assert ranked["decile"].min() == 1
    assert ranked["decile"].max() == 10


def test_decile_returns_are_monotone():
    frame = make_perfect_rank_frame()

    ranked = assign_daily_deciles(
        frame
    )

    daily = daily_decile_returns(
        ranked
    )

    stats = decile_statistics(
        daily,
        horizon=1,
    )

    deciles = stats[
        stats["decile"] != "D10-D1"
    ]

    means = deciles[
        "mean_period_return"
    ].to_numpy()

    assert np.all(
        np.diff(means) > 0
    )


def test_long_short_is_positive():
    result = evaluate_cross_section(
        make_perfect_rank_frame(),
        horizon=1,
    )

    spread = (
        result[
            "decile_statistics"
        ]
        .set_index("decile")
        .loc[
            "D10-D1",
            "mean_period_return",
        ]
    )

    assert spread > 0


def test_rank_ic_is_one_for_perfect_rank():
    frame = make_perfect_rank_frame()

    ranked = assign_daily_deciles(
        frame
    )

    ic = daily_rank_ic(
        ranked
    )

    assert np.allclose(
        ic["rank_ic"],
        1.0,
    )

    summary = summarize_rank_ic(
        ic,
        horizon=1,
    )

    assert np.isclose(
        summary["mean_ic"],
        1.0,
    )

    assert np.isclose(
        summary["hit_rate"],
        1.0,
    )


def test_information_ratio_per_decile_exists():
    result = evaluate_cross_section(
        make_perfect_rank_frame(),
        horizon=5,
    )

    stats = result[
        "decile_statistics"
    ]

    assert (
        "information_ratio"
        in stats.columns
    )

    assert len(stats) == 11


def make_payoff_frame(
    horizon: int,
    n_dates: int = 80,
    n_stocks: int = 100,
) -> pd.DataFrame:
    rows = []

    dates = pd.bdate_range(
        "2024-01-02",
        periods=n_dates + horizon,
    )

    for t in range(n_dates):
        date = dates[t]
        end_date = dates[t + horizon]

        for security in range(
            n_stocks
        ):
            score = (
                security
                / (n_stocks - 1)
            )

            realized = (
                -0.01
                + 0.02 * score
            )

            rows.append(
                {
                    "security_id":
                        security,

                    "date":
                        date,

                    "target_end_date":
                        end_date,

                    "predicted_probability":
                        score,

                    "forward_relative_return":
                        realized,

                    "target":
                        int(realized > 0),
                }
            )

    return pd.DataFrame(rows)


def test_payoff_indices_start_at_100():
    from open_equity_data.research.cross_sectional_metrics import (
        staggered_payoff_indices,
    )

    frame = make_payoff_frame(
        horizon=5
    )

    ranked = assign_daily_deciles(
        frame
    )

    indices = staggered_payoff_indices(
        ranked,
        horizon=5,
    )

    starts = (
        indices
        .sort_values("date")
        .groupby("series")
        .first()
    )

    assert np.allclose(
        starts["index_level"],
        100.0,
    )


def test_payoff_indices_exist_for_all_deciles():
    from open_equity_data.research.cross_sectional_metrics import (
        staggered_payoff_indices,
    )

    frame = make_payoff_frame(
        horizon=20
    )

    ranked = assign_daily_deciles(
        frame
    )

    indices = staggered_payoff_indices(
        ranked,
        horizon=20,
    )

    expected = {
        f"D{i}"
        for i in range(1, 11)
    } | {
        "D10-D1"
    }

    assert set(
        indices["series"].unique()
    ) == expected


def test_perfect_signal_top_decile_outperforms_bottom():
    from open_equity_data.research.cross_sectional_metrics import (
        staggered_payoff_indices,
    )

    frame = make_payoff_frame(
        horizon=10
    )

    ranked = assign_daily_deciles(
        frame
    )

    indices = staggered_payoff_indices(
        ranked,
        horizon=10,
    )

    final = (
        indices
        .sort_values("date")
        .groupby("series")
        .last()["index_level"]
    )

    assert final["D10"] > 100.0
    assert final["D1"] < 100.0
    assert final["D10"] > final["D1"]


def test_one_day_index_compounds_sequentially():
    from open_equity_data.research.cross_sectional_metrics import (
        _staggered_series_index,
    )

    dates = pd.bdate_range(
        "2024-01-02",
        periods=4,
    )

    returns = pd.DataFrame(
        {
            "date": dates[:3],
            "target_end_date":
                dates[1:4],
            "period_return":
                [0.10, 0.10, 0.10],
        }
    )

    index = _staggered_series_index(
        returns,
        horizon=1,
        series_name="test",
    )

    assert np.isclose(
        index.iloc[0][
            "index_level"
        ],
        100.0,
    )

    assert np.isclose(
        index.iloc[-1][
            "index_level"
        ],
        100.0 * (1.10 ** 3),
    )
