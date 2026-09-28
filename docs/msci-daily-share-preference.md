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
This is a **security ID × priced date** table: it retains every dated
reconciled price row, even when all share candidates are null. The three
`*_current_shares_candidate` columns show the eligible carried values for
MSCI, manual and EODHD on that date; `selected_shares_candidate` and
`selected_source` show which value won. The source's observation or filing
date, source document, close and candidate market cap are available on the
same row. It does not manufacture values on weekends or other dates without
a priced stock observation.

The builder creates `bronze.eodhd_share_manual_adjustment` as an explicit
**security ID × priced date** manual-source table. Each row records its date,
positive sourced share count, as-of and publication dates, source document
identity/URL, excerpt and ingestion time. An optional four-field target
(provider symbol, period date, filing date and original count), together with
security ID and ticker, identifies an exact erroneous EODHD observation.
Duplicate manual counts on one security/date fail the build. Populating rows
is an explicit source review decision; the builder does **not** infer
corrections from ratios. Original EODHD Bronze observations are never edited.

At each priced date, Silver joins the dated manual row after an eligible MSCI
snapshot and before EODHD. The manual daily table is populated only for dates
from the source publication through day 365, so the carry is explicit there.
It retains original EODHD shares, manual shares, and source document metadata
in separate columns. If a manual row targets a bad EODHD observation, that
original value stays ineligible even after the manual value expires; the
selected count then becomes null unless another eligible source exists. A
manual row without an EODHD target can fill a missing-source period.

For GLSPT, `python -m open_equity_data.populate_glspt_manual_shares` stages
every price date from the start of subunit trading (2021-05-10) through its
last Nasdaq trading date (2022-07-13). It prints the source-period counts
without writing rows. Add `--apply` to replace that stock's two known
source-document rows in Bronze and rebuild the Silver market-cap candidate
transactionally. The SEC April 2021 8-K establishes 16,000,000 IPO units plus
750,000 over-allotment units, each containing one subunit; the April 15, 2022
8-K reports 3,801,787 redemptions and **12,948,213 remaining public
subunits**. The first count applies to GLSPT price dates through April 14,
2022 and the second from April 15 through its last trading date. The latter
filing was accepted at 09:25 ET on April 15. Source publication and dated
share values are repeated with their SEC URLs on the relevant Bronze rows.
The 2020 prospectus weighted-average share figure is not used. This is a
point-in-time public-subunit count proxy; the actual July 12 merger
redemptions were reported later, so the July 13 value remains the latest
published public-subunit count, not a claim of the eventual closing count.

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
