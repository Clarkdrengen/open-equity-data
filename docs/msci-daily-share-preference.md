# Dated MSCI/EODHD shares and market cap (Silver candidate)

The share-source priority is **MSCI, then sourced manual adjustment, then
EODHD**, with each dated count carried forward up to **365 calendar days**.
The MSCI files represent the close at the end of their calculation
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

The builder also creates an initially empty
`bronze.eodhd_share_manual_adjustment` table. Each row records a positive
sourced share count, as-of date, source publication date, source document
identity/URL, excerpt and ingestion time. An optional four-field target
(provider symbol, period date, filing date and original count), together with
security ID and ticker, identifies an exact erroneous EODHD observation.
Duplicate targets or multiple manual counts on one issue/publication date
fail the build. Inserting a row is an explicit source review decision; the
builder does **not** infer corrections from ratios or automatically insert
a SEC filing value. Original EODHD Bronze observations are never edited.

At each priced date, Silver takes the latest available manual publication,
carried through day 365, after an eligible MSCI snapshot and before EODHD.
It retains original EODHD shares, manual shares, and source document metadata
in separate columns. If a manual row targets a bad EODHD observation, that
original value stays ineligible even after the manual value expires; the
selected count then becomes null unless another eligible source exists. A
manual row without an EODHD target can fill a missing-source period. No row
has been inserted for GLSPT: the prospectus's 2020 weighted-average figure
does not establish its July 2022 subunit count. Its original EODHD Bronze
value still needs to be inspected.

The snapshot candidate combines M15D and M15E source lineage only for an
exact date/code/ISIN single-issue match and one positive RIF Closing-share
value. From its month-end observation date through day 365, MSCI has priority
and its shares are adjusted for intervening reconciled splits from the anchor
price date. The manual source is next. Otherwise, the latest positive EODHD
balance-sheet count may be used from its filing date through day 365, subject
to the existing ticker identity ambiguity screen and exact-observation
invalidation. Cap is dated reconciled close times selected shares; otherwise
it is null.

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
