# PIT share carry sensitivity

**Validation failure:** The full-universe top-issue review found impossible
market caps (including GLSPT near $169 trillion, NVDA near $32 trillion,
and NFLX near $4–5 trillion). The derived market-cap and weighted-return
candidate tables and index must not be used as economic results. Run
`python -m open_equity_data.audit_market_cap_outliers` to inspect the exact
price, Bronze EODHD share observation, split multiplier, and security
classification for representative rows before choosing a correction.

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
database to build the derived Silver share candidate, its daily market-cap
candidate, and the market-level return candidate, and print status and recovery
counts plus 540-day daily coverage. These are new derived tables only.
The daily market return uses the previous session's market cap to weight each
eligible return. It also records the equal-weight return among exactly those
covered issues, separately from the equal-weight full-universe return. This
makes coverage-driven changes visible when comparing weighting approaches.
Compare market-cap-weighted
returns under 365/540/730 day limits after issue-specific SEC shares are
resolved and the affected securities are reviewed. Price and return gaps
are never imputed by this share policy. Rolling volume features require valid
observations; the separate missing-volume-window fix addresses this.

Limitations to review: filed date has no intraday publication time; the
existing pipeline treats that date as available at the close. Share counts
can change materially during long filing gaps. A split before a security's
first available split-factor date may be unobservable in this calculation;
the source period and estimated factor remain visible for inspection.

## Indexed aggregate market cap

After building the market-cap candidate, run
`python -m open_equity_data.export_aggregate_market_cap_index`. It creates
`silver.research_aggregate_market_cap_index_candidate`, a daily CSV, and an
SVG chart under `artifacts/research/market_cap_candidate`. The aggregate is
the sum of eligible security-level close times estimated shares for each age
window. Each series equals 100 on the first shared date with a positive
aggregate cap under all three windows. Earlier dates retain null indices.
The CSV records daily covered and eligible issue counts and coverage fractions.

The index is a **level of measured covered market capitalization**. New
listings, delistings, share issuance, and changing data coverage affect the
sum; it must not be described as an investable market return or a fixed-universe
price index. The 540-day coverage in the chart counts issues, not their missing
economic weight. Multi-issue candidates remain excluded until their
issue-specific shares can be resolved.
