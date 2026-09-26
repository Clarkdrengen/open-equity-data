# PIT share carry sensitivity

`silver.security_daily_share_carry_candidate` retains the original EODHD
quarterly share count, fiscal period date, filing date, age, and source. It
re-expresses the filed count in shares on each market date using the ratio of
reconciled cumulative split factors. The count is available starting on its
filing date, consistent with the existing PIT convention. There is no
backfill before the first filed observation or use of a later filing to choose
an earlier value.

The candidate exposes 365, 540, and 730 calendar day limits. The 730 day
column is an intentionally liberal sensitivity case, not yet the canonical
backtest weight. It flags ticker identity ambiguity and holds out every
security appearing in the multi-listed-issue candidate table: an EODHD issuer
total must not be duplicated across share classes. That table is a candidate
detector and may include false positives; the holdout is deliberately
conservative pending issue-specific resolution.

Run `python -m open_equity_data.audit_share_carry_candidate` against the local
database to build the derived Silver candidate and print status and recovery
counts. This changes only that derived table. Compare market-cap-weighted
returns under 365/540/730 day limits after issue-specific SEC shares are
resolved and the affected securities are reviewed. Price and return gaps
are never imputed by this share policy. Rolling volume features require valid
observations; the separate missing-volume-window fix addresses this.

Limitations to review: filed date has no intraday publication time; the
existing pipeline treats that date as available at the close. Share counts
can change materially during long filing gaps. A split before a security's
first available split-factor date may be unobservable in this calculation;
the source period and estimated factor remain visible for inspection.
