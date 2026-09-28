# Dated MSCI/EODHD shares and market cap (Silver candidate)

Nick specified the share-source priority MSCI, then EODHD, then another
approved source, with each dated count carried forward up to **365 calendar
days**. The MSCI files represent the close at the end of their calculation
month: the count applies at that month-end close, with **no reporting lag**.
A month-end date without a priced session cannot be applied to an earlier
price date. No later snapshot is backfilled into earlier dates.

Run after the RIF share extraction and both family overlap audits:

```bash
python -m open_equity_data.build_msci_daily_share_preference
```

The command builds `silver.msci_preferred_share_snapshot_candidate` and one
`silver.security_daily_market_cap_source_priority_candidate`. It removes the
obsolete 1/5/22-session lag tables. The daily base is **every dated row in
`silver.security_daily_ohlcv_reconciled`**, without filtering to securities
with a future MSCI match, a later-year constituent set or research-universe
eligibility. The selected share and price source are recorded separately.

The snapshot candidate combines M15D and M15E source lineage only for an
exact date/code/ISIN single-issue match and one positive RIF Closing-share
value. From its month-end observation date through day 365, MSCI has priority
and its shares are adjusted for intervening reconciled splits from the anchor
price date. Otherwise, the latest positive EODHD balance-sheet count may be
used from its filing date through day 365, subject to the existing ticker
identity ambiguity screen. Cap is dated reconciled close times selected shares;
otherwise it is null. The code does not add an unapproved third share source.

The original open-source Dolt/DoltHub import supplied Bronze `ohlcv`, `split`,
`dividend`, and `symbol`: the starting price/action/reference source, not a
verified outstanding-share source. EODHD also supplies some corrected or
missing prices. `price_source` remains distinct from `selected_source` and
`eodhd_share_source` in the cap candidate.

The command reports source coverage, largest candidate cap by selected share
source, and the peak observation for each of the 12 distinct issues with the
largest EODHD caps. The latter includes ticker/name, instrument/exchange,
price, shares, filing/period dates and both source lineages to diagnose
issuer totals, units, ADRs, currency and split-basis problems. It changes no
canonical shares or benchmark and builds **no deciles**. The old PR #29
weighted aggregate remains invalid; this is a source-quality exercise.
