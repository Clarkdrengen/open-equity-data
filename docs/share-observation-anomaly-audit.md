# Universe-wide share observation audit

Run after `build_msci_daily_share_preference`:

```bash
python -m open_equity_data.audit_share_observation_anomalies --limit 30
```

This rebuilds `silver.share_observation_anomaly_audit` from the full priced
market-cap candidate, including EODHD source records that were not selected.
Its grain is security ID plus provider symbol, period date, filing date and
raw shares. One row reports all priced dates reached by that observation,
its selected days and peak selected and raw implied market caps. It does not
change Bronze, selected Silver shares or market caps.

The within-security robust z-score uses log shares, a median and median
absolute deviation. Comparable source shares are divided by the reconciled
split multiplier to put observations on one diagnostic basis. A high z-score
requires at least a 1.5x deviation from the issue median: a tiny median
absolute deviation must not classify ordinary gradual buybacks as an error.
The adjacent
ratio detects large jumps when dispersion is zero. MSCI and sourced manual
comparisons use shares on the same priced date and only when the EODHD basis
is normalized. Sources with unknown split basis are retained but are not
treated as confirmed time-series or cross-source discrepancies. A large
selected cap without a dated independent comparison gets a separate review
flag, since a consistently wrong history can have no within-stock anomaly.

The CLI prints a reason summary and three queues, with **one source record
per security** in each: selected statistical or cross-source signals, large
selected caps with no independent comparison, and unselected source signals.
Selected signals rank by robust z-score by default (`--rank impact` instead
ranks them by selected cap); large caps rank by selected cap, and unselected
signals rank by raw implied cap. The full
Silver table retains every source record for deeper analysis. Scores identify
records to inspect; they do not
approve a correction, infer a universal 1,000x scale or establish that a
large market cap is wrong. Review one source record and its affected span at
a time. Confirmed manual replacements go exclusively through dated rows in
`bronze.eodhd_share_manual_adjustment`, followed by a Silver rebuild.

This audit does not diagnose wrong exchange eligibility, price currency or
identity. Those require distinct source-backed checks before using market
caps for research-universe aggregates.
