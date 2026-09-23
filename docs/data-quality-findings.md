# Data Quality Findings

## Dolt OHLCV and corporate actions

The Dolt source is useful but is not research-ready without validation.

Observed issues include:

- Incorrect split ratios.
- Duplicate split events.
- OHLCV observations on dates when the US equity market was closed.
- Ticker recycling.
- Missing expected trading sessions.
- Current-state symbol metadata that should not be interpreted as historical security metadata.

## Closed-session observations

A material number of Dolt OHLCV rows occur on dates when the XNYS trading calendar was closed.

These include:

- Exact duplicates of adjacent valid sessions.
- Hybrid observations combining fields from neighbouring sessions.
- Other anomalous closed-session observations.

The Silver clean OHLCV layer excludes all observations on non-expected trading sessions while preserving them in Bronze.

## Missing expected sessions

For the three currently validated lineages, 40 expected-session observations were missing from Dolt:

- BCIC_1
- META_1
- VTAK_1

EODHD returned an observation for all 40 dates.

Of these:

- 37 were retrieved using the historically appropriate ticker.
- 3 FB-era observations required lookup under `META.US`.

## EODHD successor-ticker behaviour

EODHD may consolidate historical data under the latest ticker in a security lineage.

This is useful for recovering observations after ticker changes but cannot be treated as semantically identical to historical-ticker data.

Testing RMED versus VTAK showed:

- Raw OHLC values can remain broadly consistent.
- OHLC precision can be reduced under the successor ticker.
- `adjusted_close` may incorporate later reverse splits.
- Volume may also be transformed by later corporate actions.

Therefore successor-ticker data is treated as fallback evidence, not automatically as equivalent raw history.

## FB / META validation

EODHD returned no observation for `FB.US` on 2019-08-23 but returned the corresponding historical observation under `META.US`.

Comparison of surrounding dates showed exact OHLC agreement between:

- Dolt observations stored under historical ticker FB.
- EODHD observations retrieved under META.

Volume differed only by immaterial amounts on overlapping dates.

This supports use of the META lineage fallback for the three missing FB-era observations.

## RMED 2023-01-09

EODHD returned:

- Open: 5.89
- High: 5.89
- Low: 5.89
- Close: 5.89
- Volume: 0

The observation is not a simple previous-close carry-forward, but it also does not represent an ordinary traded OHLC bar.

It is retained in the reconciled data with `research_eligible = false`.
