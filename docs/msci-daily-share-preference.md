# Dated MSCI/EODHD shares and market cap (Silver candidate)

The agreed priority is MSCI, then EODHD, then another approved source. Both
known sources can carry a dated observation forward for at most **365 calendar
days**. No future observation is backfilled into earlier dates. The third
source has not been identified and is therefore not silently inferred from an
unreviewed SEC class-share candidate. A row with neither source has null shares
and market cap. No deciles or backtests are built by this module.

The original open-source Dolt/DoltHub import supplied the project's Bronze
`ohlcv`, `split`, `dividend`, and `symbol` tables. It is the starting price and
corporate-action source, not a verified outstanding-share source in the
current pipeline. The cap candidate retains `price_source` independently of
the selected share source, since a Dolt price can be paired with an MSCI or
EODHD share count. EODHD also supplies some corrected or missing prices.

Run after the RIF extraction and both family overlap audits:

```bash
python -m open_equity_data.build_msci_daily_share_preference
```

The daily tables `silver.msci_daily_share_preference_lag{1,5,22}_candidate`
start from **every dated row of `silver.security_daily_ohlcv_reconciled`**.
There is no join to securities that happen to be present one or two years
later, no conditioning on an eventual MSCI match, and no research-universe
eligibility filter in the daily share/cap construction. The snapshot candidate
uses distinct M15D and M15E source lineage and single-issue matched RIF
Closing-share evidence. MSCI publication timestamps are unknown; first,
fifth and twenty-second price sessions after the month-end observation are
separate availability sensitivities, not asserted actual release dates.

Within each sensitivity, MSCI is selected when the latest eligible snapshot
is at most 365 days old, with positive shares and dated split factors.
The shares are rolled forward with reconciled split multipliers. Otherwise,
the latest positive EODHD balance-sheet count is selected only from its filing
date through 365 days later, with the existing ticker-identity ambiguity
screen. Market cap is dated reconciled closing price times the selected share
count. The rows retain share source, filing or snapshot date, count, price,
and selection status. The derived security cap is a **candidate**, especially
for EODHD issuer totals on multi-class issuers, ADR basis differences, and
possible historical split normalization. The daily Silver base does not
solve those source-basis issues.

The command reports dated issue-day counts, priced counts and largest
single-issue cap by source and lag. Inspect outliers and choose the MSCI
release-timing policy and third source with Nick before promoting the cap
series. Existing PR #29 weighted aggregate and decile calculations remain
invalid; this module does not create or update them. Source bytes stay in
Bronze and confidential MSCI records remain on Nick's Mac.
