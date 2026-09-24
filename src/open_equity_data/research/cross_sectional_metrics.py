"""
Cross-sectional evaluation for the multi-horizon return-prediction benchmark.

This module evaluates whether model predictions rank future equity returns.

The statistical analysis uses every eligible signal date. Because forward
returns overlap for horizons greater than one day, inference uses
horizon-specific HAC / Newey-West standard errors.

Portfolio wealth indices are handled separately. Naively compounding
overlapping h-day forward returns would double-count capital.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


VALID_HORIZONS = (1, 5, 10, 20, 60)
N_DECILES = 10
TRADING_DAYS_PER_YEAR = 252


def hac_lag(horizon: int) -> int:
    if horizon not in VALID_HORIZONS:
        raise ValueError(
            f"Unsupported horizon {horizon}; "
            f"expected one of {VALID_HORIZONS}"
        )

    return max(horizon - 1, 0)


def periods_per_year(horizon: int) -> float:
    return TRADING_DAYS_PER_YEAR / horizon


def validate_prediction_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "security_id",
        "date",
        "predicted_probability",
        "forward_relative_return",
        "target",
    }

    missing = required - set(frame.columns)

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing))
        )

    out = frame.copy()

    out["date"] = pd.to_datetime(out["date"])

    out = out.dropna(
        subset=[
            "security_id",
            "date",
            "predicted_probability",
            "forward_relative_return",
            "target",
        ]
    )

    if not out["predicted_probability"].between(
        0.0,
        1.0,
    ).all():
        raise ValueError(
            "predicted_probability must lie in [0, 1]"
        )

    if out.duplicated(
        ["security_id", "date"]
    ).any():
        raise ValueError(
            "Duplicate security_id/date observations"
        )

    return out


def assign_daily_deciles(
    frame: pd.DataFrame,
    n_deciles: int = N_DECILES,
) -> pd.DataFrame:
    """
    Rank securities independently within each date.

    D1 = lowest predicted probability.
    D10 = highest predicted probability.

    Dates with fewer than n_deciles observations are discarded.
    """

    if n_deciles < 2:
        raise ValueError("n_deciles must be >= 2")

    x = validate_prediction_frame(frame)

    counts = x.groupby("date")[
        "security_id"
    ].transform("size")

    x = x.loc[counts >= n_deciles].copy()

    rank = x.groupby("date")[
        "predicted_probability"
    ].rank(
        method="first",
        pct=True,
    )

    x["decile"] = np.minimum(
        np.ceil(rank * n_deciles).astype(int),
        n_deciles,
    )

    return x


def daily_decile_returns(
    ranked: pd.DataFrame,
) -> pd.DataFrame:
    """
    Equal-weight forward relative return within each date/decile.
    """

    required = {
        "date",
        "decile",
        "forward_relative_return",
        "security_id",
    }

    missing = required - set(ranked.columns)

    if missing:
        raise ValueError(
            "Missing ranked columns: "
            + ", ".join(sorted(missing))
        )

    return (
        ranked
        .groupby(
            ["date", "decile"],
            observed=True,
        )
        .agg(
            decile_return=(
                "forward_relative_return",
                "mean",
            ),
            n_stocks=(
                "security_id",
                "size",
            ),
        )
        .reset_index()
        .sort_values(
            ["date", "decile"]
        )
        .reset_index(drop=True)
    )


def newey_west_mean_test(
    returns: pd.Series | np.ndarray,
    maxlags: int,
) -> tuple[float, float]:
    """
    HAC estimate of the mean-return t-statistic and standard error.
    """

    values = np.asarray(
        pd.Series(returns).dropna(),
        dtype=float,
    )

    if len(values) < 2:
        return np.nan, np.nan

    X = np.ones(
        (len(values), 1),
        dtype=float,
    )

    result = sm.OLS(
        values,
        X,
    ).fit(
        cov_type="HAC",
        cov_kwds={
            "maxlags": maxlags,
        },
    )

    return (
        float(result.tvalues[0]),
        float(result.bse[0]),
    )


@dataclass(frozen=True)
class DecileStatistics:
    decile: int | str
    observations: int
    mean_period_return: float
    annualized_return: float
    annualized_volatility: float
    information_ratio: float
    newey_west_t: float
    newey_west_se: float
    average_n_stocks: float


def summarize_return_series(
    returns: pd.Series,
    horizon: int,
    average_n_stocks: float,
    label: int | str,
) -> DecileStatistics:
    values = returns.dropna().astype(float)

    n = len(values)

    if n == 0:
        return DecileStatistics(
            decile=label,
            observations=0,
            mean_period_return=np.nan,
            annualized_return=np.nan,
            annualized_volatility=np.nan,
            information_ratio=np.nan,
            newey_west_t=np.nan,
            newey_west_se=np.nan,
            average_n_stocks=average_n_stocks,
        )

    ppy = periods_per_year(horizon)

    mean_return = float(values.mean())

    if n > 1:
        period_vol = float(
            values.std(ddof=1)
        )
    else:
        period_vol = np.nan

    annualized_return = mean_return * ppy

    annualized_volatility = (
        period_vol * np.sqrt(ppy)
        if np.isfinite(period_vol)
        else np.nan
    )

    if (
        np.isfinite(annualized_volatility)
        and annualized_volatility > 0
    ):
        information_ratio = (
            annualized_return
            / annualized_volatility
        )
    else:
        information_ratio = np.nan

    nw_t, nw_se = newey_west_mean_test(
        values,
        maxlags=hac_lag(horizon),
    )

    return DecileStatistics(
        decile=label,
        observations=n,
        mean_period_return=mean_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        information_ratio=information_ratio,
        newey_west_t=nw_t,
        newey_west_se=nw_se,
        average_n_stocks=float(
            average_n_stocks
        ),
    )


def decile_statistics(
    daily_returns: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    """
    Statistics for D1...D10 and D10-D1.
    """

    rows: list[dict] = []

    for decile in range(
        1,
        N_DECILES + 1,
    ):
        subset = daily_returns.loc[
            daily_returns["decile"]
            == decile
        ]

        stats = summarize_return_series(
            returns=subset[
                "decile_return"
            ],
            horizon=horizon,
            average_n_stocks=subset[
                "n_stocks"
            ].mean(),
            label=f"D{decile}",
        )

        rows.append(stats.__dict__)

    wide = daily_returns.pivot(
        index="date",
        columns="decile",
        values="decile_return",
    )

    if 1 in wide.columns and 10 in wide.columns:
        spread = (
            wide[10] - wide[1]
        ).dropna()

        avg_n = daily_returns.loc[
            daily_returns["decile"].isin(
                [1, 10]
            ),
            "n_stocks",
        ].mean()

        stats = summarize_return_series(
            returns=spread,
            horizon=horizon,
            average_n_stocks=avg_n,
            label="D10-D1",
        )

        rows.append(stats.__dict__)

    return pd.DataFrame(rows)


def daily_rank_ic(
    ranked: pd.DataFrame,
) -> pd.DataFrame:
    """
    Daily cross-sectional Spearman rank IC.

    Correlates predicted probability with realized forward relative return.
    """

    rows = []

    for date, group in ranked.groupby(
        "date",
        sort=True,
    ):
        if len(group) < 3:
            continue

        ic = group[
            [
                "predicted_probability",
                "forward_relative_return",
            ]
        ].corr(
            method="spearman"
        ).iloc[0, 1]

        rows.append(
            {
                "date": date,
                "rank_ic": ic,
                "n_stocks": len(group),
            }
        )

    return pd.DataFrame(rows)


def summarize_rank_ic(
    ic: pd.DataFrame,
    horizon: int,
) -> dict[str, float | int]:
    values = ic["rank_ic"].dropna()

    n = len(values)

    if n == 0:
        return {
            "observations": 0,
            "mean_ic": np.nan,
            "std_ic": np.nan,
            "icir": np.nan,
            "newey_west_t": np.nan,
            "hit_rate": np.nan,
        }

    mean_ic = float(values.mean())

    std_ic = (
        float(values.std(ddof=1))
        if n > 1
        else np.nan
    )

    icir = (
        mean_ic / std_ic
        if (
            np.isfinite(std_ic)
            and std_ic > 0
        )
        else np.nan
    )

    nw_t, _ = newey_west_mean_test(
        values,
        maxlags=hac_lag(horizon),
    )

    return {
        "observations": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "icir": icir,
        "newey_west_t": nw_t,
        "hit_rate": float(
            (values > 0).mean()
        ),
    }


def decile_monotonicity(
    stats: pd.DataFrame,
) -> dict[str, float | bool]:
    """
    Quick monotonicity diagnostic.

    Spearman correlation between D1...D10 rank and each decile's
    mean forward relative return.
    """

    x = stats.loc[
        stats["decile"].isin(
            [f"D{i}" for i in range(1, 11)]
        )
    ].copy()

    x["decile_number"] = (
        x["decile"]
        .str.replace("D", "", regex=False)
        .astype(int)
    )

    if len(x) < 3:
        return {
            "spearman_decile_return":
                np.nan,
            "strictly_monotone":
                False,
        }

    rho = x[
        [
            "decile_number",
            "mean_period_return",
        ]
    ].corr(
        method="spearman"
    ).iloc[0, 1]

    ordered = (
        x.sort_values(
            "decile_number"
        )["mean_period_return"]
        .to_numpy()
    )

    strictly_monotone = bool(
        np.all(
            np.diff(ordered) > 0
        )
    )

    return {
        "spearman_decile_return":
            float(rho),
        "strictly_monotone":
            strictly_monotone,
    }


def long_short_decomposition(
    stats: pd.DataFrame,
) -> dict[str, float]:
    lookup = (
        stats
        .set_index("decile")[
            "mean_period_return"
        ]
        .to_dict()
    )

    d10 = lookup.get(
        "D10",
        np.nan,
    )

    d1 = lookup.get(
        "D1",
        np.nan,
    )

    return {
        "long_leg_mean_return":
            float(d10),

        "short_leg_mean_return":
            float(-d1),

        "long_short_mean_return":
            float(d10 - d1),
    }


def evaluate_cross_section(
    frame: pd.DataFrame,
    horizon: int,
) -> dict:
    """
    Complete model-independent cross-sectional evaluation.
    """

    ranked = assign_daily_deciles(
        frame
    )

    decile_daily = daily_decile_returns(
        ranked
    )

    decile_stats = decile_statistics(
        decile_daily,
        horizon=horizon,
    )

    ic_daily = daily_rank_ic(
        ranked
    )

    ic_summary = summarize_rank_ic(
        ic_daily,
        horizon=horizon,
    )

    monotonicity = decile_monotonicity(
        decile_stats
    )

    decomposition = (
        long_short_decomposition(
            decile_stats
        )
    )

    return {
        "ranked": ranked,
        "daily_decile_returns":
            decile_daily,
        "decile_statistics":
            decile_stats,
        "daily_rank_ic":
            ic_daily,
        "rank_ic_summary":
            ic_summary,
        "monotonicity":
            monotonicity,
        "long_short_decomposition":
            decomposition,
    }


# ============================================================
# Staggered payoff indices
# ============================================================


def _staggered_series_index(
    returns: pd.DataFrame,
    horizon: int,
    series_name: str,
) -> pd.DataFrame:
    """
    Construct an equal-capital staggered payoff index.

    Input columns:
        date
        target_end_date
        period_return

    For an h-day horizon, signal dates are assigned to h sleeves.
    Each sleeve therefore holds non-overlapping h-day observations.

    Capital is allocated equally across sleeves. Sleeves that have not
    yet realized their first investment remain at 100 (cash).

    This avoids the invalid practice of compounding overlapping h-day
    forward returns as if each observation represented fresh capital.
    """

    if horizon not in VALID_HORIZONS:
        raise ValueError(
            f"Unsupported horizon {horizon}"
        )

    required = {
        "date",
        "target_end_date",
        "period_return",
    }

    missing = required - set(
        returns.columns
    )

    if missing:
        raise ValueError(
            "Missing payoff-index columns: "
            + ", ".join(sorted(missing))
        )

    x = returns.copy()

    x["date"] = pd.to_datetime(
        x["date"]
    )

    x["target_end_date"] = pd.to_datetime(
        x["target_end_date"]
    )

    x = (
        x
        .dropna(
            subset=[
                "date",
                "target_end_date",
                "period_return",
            ]
        )
        .sort_values(
            [
                "date",
                "target_end_date",
            ]
        )
        .reset_index(drop=True)
    )

    if x.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "series",
                "horizon",
                "index_level",
            ]
        )

    if (
        x["period_return"]
        < -1.0
    ).any():
        raise ValueError(
            "period_return below -100%"
        )

    signal_dates = (
        x["date"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    sleeve_lookup = {
        date: i % horizon
        for i, date
        in enumerate(signal_dates)
    }

    x["sleeve"] = (
        x["date"]
        .map(sleeve_lookup)
        .astype(int)
    )

    start_date = min(signal_dates)

    realization_dates = (
        x["target_end_date"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    timeline = pd.DatetimeIndex(
        sorted(
            set(
                [start_date]
                + realization_dates
            )
        )
    )

    sleeve_paths = []

    for sleeve in range(horizon):
        s = (
            x.loc[
                x["sleeve"] == sleeve,
                [
                    "target_end_date",
                    "period_return",
                ],
            ]
            .sort_values(
                "target_end_date"
            )
            .copy()
        )

        if s.empty:
            path = pd.Series(
                100.0,
                index=timeline,
                dtype=float,
            )

            sleeve_paths.append(path)
            continue

        # A sleeve must never contain overlapping observations.
        if s[
            "target_end_date"
        ].duplicated().any():
            raise ValueError(
                "Duplicate realization date "
                "inside payoff sleeve"
            )

        wealth = (
            100.0
            * (
                1.0
                + s["period_return"].astype(float)
            ).cumprod()
        )

        path = pd.Series(
            wealth.to_numpy(),
            index=pd.DatetimeIndex(
                s["target_end_date"]
            ),
            dtype=float,
        )

        # Before the sleeve's first realization its capital
        # remains uninvested at 100.
        path = (
            path
            .reindex(timeline)
            .ffill()
            .fillna(100.0)
        )

        sleeve_paths.append(path)

    matrix = np.column_stack(
        [
            path.to_numpy()
            for path in sleeve_paths
        ]
    )

    aggregate = matrix.mean(
        axis=1
    )

    result = pd.DataFrame(
        {
            "date": timeline,
            "series": series_name,
            "horizon": horizon,
            "index_level": aggregate,
        }
    )

    # Explicitly anchor every index at 100.
    result.loc[
        result.index[0],
        "index_level",
    ] = 100.0

    return result


def staggered_payoff_indices(
    ranked: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    """
    Construct indexed payoff series starting at 100 for:

        D1 ... D10
        D10-D1

    Decile series use equal-weight cross-sectional forward relative
    returns.

    D10-D1 is included as a spread-payoff diagnostic. It should not be
    interpreted as a fully specified self-financing executable strategy;
    turnover, financing, borrow and transaction costs are handled in the
    later portfolio layer.
    """

    required = {
        "security_id",
        "date",
        "target_end_date",
        "decile",
        "forward_relative_return",
    }

    missing = required - set(
        ranked.columns
    )

    if missing:
        raise ValueError(
            "Missing ranked payoff columns: "
            + ", ".join(sorted(missing))
        )

    x = ranked.copy()

    x["date"] = pd.to_datetime(
        x["date"]
    )

    x["target_end_date"] = pd.to_datetime(
        x["target_end_date"]
    )

    # For a given forecast horizon, every security prediction
    # made on the same signal date should realize on the same
    # target end date.
    end_date_counts = (
        x.groupby("date")[
            "target_end_date"
        ]
        .nunique()
    )

    if (
        end_date_counts > 1
    ).any():
        raise ValueError(
            "A signal date maps to multiple "
            "target_end_dates"
        )

    daily = (
        x
        .groupby(
            [
                "date",
                "target_end_date",
                "decile",
            ],
            observed=True,
        )
        .agg(
            period_return=(
                "forward_relative_return",
                "mean",
            ),
            n_stocks=(
                "security_id",
                "size",
            ),
        )
        .reset_index()
    )

    outputs = []

    for decile in range(
        1,
        N_DECILES + 1,
    ):
        d = daily.loc[
            daily["decile"]
            == decile,
            [
                "date",
                "target_end_date",
                "period_return",
            ],
        ]

        outputs.append(
            _staggered_series_index(
                returns=d,
                horizon=horizon,
                series_name=f"D{decile}",
            )
        )

    wide = daily.pivot(
        index=[
            "date",
            "target_end_date",
        ],
        columns="decile",
        values="period_return",
    )

    if (
        1 in wide.columns
        and 10 in wide.columns
    ):
        spread = (
            wide[10]
            - wide[1]
        ).rename(
            "period_return"
        ).reset_index()

        outputs.append(
            _staggered_series_index(
                returns=spread,
                horizon=horizon,
                series_name="D10-D1",
            )
        )

    if not outputs:
        return pd.DataFrame(
            columns=[
                "date",
                "series",
                "horizon",
                "index_level",
            ]
        )

    return (
        pd.concat(
            outputs,
            ignore_index=True,
        )
        .sort_values(
            [
                "series",
                "date",
            ]
        )
        .reset_index(drop=True)
    )
