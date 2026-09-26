# Technical Return-Prediction Benchmark

## Objective

Test whether a compact set of technical and market-state variables contains
stable information about future equity returns.

The first benchmark is intentionally simple and falsifiable. It is designed as
a comparison exercise rather than as an optimized trading strategy.

## Research universe

Primary benchmark universe:

`primary_research_eligible_exchange`

This contains common equity on NASDAQ, NYSE, AMEX / NYSE MKT that also passes
the return-data research eligibility rules.

Robustness universe:

`primary_research_eligible_broad`

Delisted securities are retained where otherwise eligible.

## Timing convention

For observation date `t`, all explanatory variables must be computable using
information available through the close of `t`.

The benchmark uses multiple forward prediction horizons:

- 1 trading day
- 5 trading days
- 10 trading days
- 20 trading days
- 60 trading days

For each horizon `h`, the continuous target is the compounded forward
market-relative gross total return:

`forward_rel_return_h =
    product(1 + security_gtr[t+1:t+h])
    / product(1 + market_gtr[t+1:t+h])
    - 1`

The corresponding classifier target is:

`target_outperform_h = 1[forward_rel_return_h > 0]`

Both the continuous forward return and binary classification label are retained
in the research table.

Forward labels begin after date `t`; no return from date `t` enters its own
target.

A forward target is populated only when all `h` required future trading-session
returns are present and research eligible. Labels must not bridge missing
observations, quarantined returns, or security-series breaks.

This is initially a predictive benchmark rather than an executable trading
backtest. Any economically implemented strategy will later require an explicit
execution convention, such as trading at the next open.

## Initial feature set

Where a feature has a meaningful trailing-window interpretation, it is
calculated over all three standard horizons:

- 14 trading sessions
- 20 trading sessions
- 60 trading sessions

No horizon is selected ex ante on the basis of apparent predictive performance.

### Immediate return

- `lag_1d_gtr`

### Trailing compounded return

- `trailing_gtr_14d`
- `trailing_gtr_20d`
- `trailing_gtr_60d`

Trailing returns are compounded rather than summed.

### Realized volatility

- `realized_vol_14d`
- `realized_vol_20d`
- `realized_vol_60d`

For a signal observed at the close of date `t`, realized volatility used to
standardize the date-`t` return is estimated using returns through `t-1`.
This prevents the return shock from mechanically changing its own volatility
denominator.

### Volatility-scaled one-day return

- `scaled_lag_1d_return_14d`
- `scaled_lag_1d_return_20d`
- `scaled_lag_1d_return_60d`

Each feature is the current one-day gross-total-return shock divided by the
corresponding trailing realized-volatility estimate.

### RSI

- `rsi_14`
- `rsi_20`
- `rsi_60`

RSI is calculated using information through the close of date `t`.

### Relative volume

- `relative_volume_14d`
- `relative_volume_20d`
- `relative_volume_60d`

Relative volume compares date-`t` volume with the trailing median volume for
the same security. The reference window excludes date `t`.

### Security-level volume surprise

- `volume_zscore_14d`
- `volume_zscore_20d`
- `volume_zscore_60d`

The volume z-score is calculated from `log1p(volume)` relative to the same
security's trailing mean and standard deviation.

The reference window excludes date `t`.

This is a time-series normalization within each security, not a
cross-sectional z-score.

An absent volume observation remains `NULL` rather than becoming zero. Both
relative-volume and volume z-score features require all observations in their
prior 14/20/60-session reference window. A volume gap does not erase valid
price or return information for that security; it makes only the affected
volume features unavailable until the reference window is complete again.

### Market state

- `market_return_1d`
- `market_relative_return_1d`

These are intentionally one-day state variables rather than mechanically
duplicated across the 14/20/60-session windows. Longer-horizon market-regime
features may be introduced later as a separate feature family.

## Feature-set philosophy

The initial feature set intentionally retains overlapping 14-, 20- and
60-session versions of the same economic state variables.

Multicollinearity is not treated as a reason for manual feature deletion in the
nonlinear benchmark models. The benchmark will instead test whether the models
can exploit or ignore correlated representations out of sample.

Raw price level, raw volume, ticker/security identifiers, cumulative wealth
index, fundamentals, sector variables and large unconstrained families of
technical indicators are excluded from the first benchmark.

## Train / validation / test split

Train:
2011-01-01 through 2022-12-31

Validation:
2023-01-01 through 2024-12-31

Test:
2025-01-01 onward

Random cross-validation is prohibited.

## Benchmark models

Initial models:

1. unconditional / base-rate classifier
2. logistic regression
3. gradient-boosted trees
4. TabPFN-3.5 classifier

TabPFN will initially be trained on a manageable temporally representative
training sample rather than the complete multi-million-row panel.

### Running the validation benchmark

Export model-ready data, then run the conventional models and TabPFN separately:

```bash
python -m open_equity_data.research.benchmark_dataset
python -m open_equity_data.research.benchmark_models
python -m pip install -e '.[tabpfn]'
python -m open_equity_data.research.benchmark_tabpfn
```

For a smaller initial experiment, pass `--horizon 1` to either model runner.
TabPFN uses `train_tabpfn.parquet`; the conventional models use
`train_large.parquet`. All models use the same validation export and evaluation
functions. Outputs appear in `artifacts/research/benchmark_v1/baselines/`.
The separate `tabpfn_validation_summary.csv` records its five horizons; each
model/horizon also retains predictions, metadata, and detailed diagnostics.

The default 100,000-row TabPFN training sample requires a suitable accelerator.
For a CPU pilot, re-export with `--tabpfn-train-rows 5000` before running the
TabPFN command. CPU inference over the default 250,000 validation rows can be
slow; `--validation-rows` changes the common validation export for all models.
TabPFN may fetch its model weights and require license acceptance on first use.
Do not inspect or export the 2025+ test period during model development.

If PyTorch MPS fails during prediction on Apple Silicon, run an isolated CPU
smoke test:

```bash
python -m open_equity_data.research.benchmark_dataset \
  --tabpfn-train-rows 5000 --validation-rows 5000 \
  --output-dir artifacts/research/benchmark_v1/cpu_smoke/datasets
python -m open_equity_data.research.benchmark_tabpfn \
  --horizon 1 --device cpu --batch-size 100 \
  --dataset-dir artifacts/research/benchmark_v1/cpu_smoke/datasets \
  --output-dir artifacts/research/benchmark_v1/cpu_smoke/results
```

The 5,000-row validation sample is too sparse on each date for reliable decile
statistics. Treat this as an execution check, not evidence of predictive or
economic performance. A Prior Labs API key is for its hosted API client;
the local `tabpfn` package uses a separate model access flow.

On a Mac with sufficient unified memory, an accelerated validation run can
cache training computations across prediction batches:

```bash
python -m open_equity_data.research.benchmark_tabpfn \
  --horizon 1 --device mps --fit-mode fit_with_cache \
  --batch-size 8192 --n-estimators 1 \
  --output-dir artifacts/research/benchmark_v1/tabpfn_mps_pilot
```

This uses the full exported validation sample. The single-estimator setting is
a speed pilot with lower ensemble diversity, so its outputs have their own
directory and metadata. Cache mode uses more device memory; if fit fails for
memory, reduce the TabPFN training sample using a separate dataset export.
This setting does not fix an MPS accelerator error in PyTorch.

## Evaluation

Primary statistical metrics:

- log loss
- Brier score
- ROC-AUC
- accuracy
- calibration

Economic diagnostics:

- mean forward excess return by predicted-probability decile
- top-minus-bottom probability-decile return spread
- stability by calendar period
- comparison across forecast horizons

No model will be judged from accuracy alone.

## Research progression

The first experiment asks whether predictive structure exists at all.

### Fixed RSI(14) comparison

Run a non-fitted technical rule on the same validation export:

```bash
python -m open_equity_data.research.benchmark_rsi --horizon 1
```

This reports two pre-specified rank directions: reversal ranks low RSI higher,
and continuation ranks high RSI higher. It also compares forward relative
returns on the same dates for RSI below 30 versus above 70. The RSI ranks are
scores, not calibrated probabilities, so log loss, Brier score and AUC are
intentionally absent. Outputs include daily IC and decile returns, threshold
event counts and paired-date Newey–West inference. The analysis uses the
sampled validation universe and remains a predictive diagnostic without
trading costs or an executable entry convention. Both directions are reported;
selecting the better direction after seeing validation requires the untouched
test period for an honest final assessment.

For a one-day comparison with the conventional baselines and a separately
saved one-estimator TabPFN MPS pilot:

```bash
python -m open_equity_data.research.compare_validation --horizon 1
```

The comparison requires all six outputs on the same full validation export.
It marks RSI rows as rank scores and leaves probability metrics blank for them.
The single-estimator TabPFN result is labeled through its run metadata and
should not be mistaken for the default ensemble configuration.

If evidence is positive, subsequent work may test:

- alternative target definitions and holding-period conventions
- broader common-equity universe
- liquidity and price robustness filters
- additional technical variables
- fundamentals and other point-in-time information
- walk-forward retraining
- executable trading assumptions

## Cross-sectional evaluation

Model predictions are evaluated as cross-sectional equity-ranking signals
separately for every forecast horizon:

- 1 trading day
- 5 trading days
- 10 trading days
- 20 trading days
- 60 trading days

On each eligible signal date, securities are ranked independently by predicted
outperformance probability and assigned to D1 through D10.

The following diagnostics are calculated independently for every
model / horizon / sample combination:

- equal-weight forward market-relative return for every decile
- annualised return for every decile
- annualised volatility for every decile
- information ratio for every decile
- Newey-West t-statistic for every decile
- D10 minus D1 spread
- separate D10 long-leg and short-D1 contributions
- cross-sectional Spearman rank information coefficient
- mean and standard deviation of IC
- IC information ratio
- Newey-West IC t-statistic
- positive-IC hit rate
- decile-return monotonicity
- average breadth per decile

HAC / Newey-West inference uses lags corresponding to overlap in the forward
return horizon:

- 1-day: 0 lags
- 5-day: 4 lags
- 10-day: 9 lags
- 20-day: 19 lags
- 60-day: 59 lags

A formal Patton-Timmermann monotonic relation test is reserved for the extended
robustness stage; the initial framework reports the full decile profile and
Spearman monotonicity diagnostic.

## Indexed decile payoff series

For every model and forecast horizon, indexed payoff series starting at 100 are
constructed for D1 through D10.

Forward returns longer than one trading day overlap across adjacent signal
dates. They therefore must not be naively compounded sequentially.

For an h-day forecast horizon, the payoff calculation instead forms h staggered
sleeves. Each sleeve enters only every h-th signal date, making the forward
return observations within a sleeve non-overlapping. Capital is allocated
equally across the sleeves and the sleeve wealth paths are combined into the
reported index.

A D10-minus-D1 spread-payoff index is also retained as a diagnostic. It is not
treated as a complete executable long-short backtest. Transaction costs,
turnover, financing, short borrow and explicit portfolio implementation are
handled in the subsequent economic layer.

## Test-set discipline

Model and methodology development uses the train and validation samples only.

The 2025 onward test period is not exported by the benchmark dataset builder
during development. Test-period predictions and cross-sectional diagnostics
will be generated only after the benchmark specification has been frozen.
