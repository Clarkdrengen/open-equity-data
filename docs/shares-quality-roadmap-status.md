# Shares and market-cap data quality: status after September 26, 2026

The figures below are from terminal results shared in the project conversation.
The repository contains the loaders and audits, but not Nick's local DuckDB or
the original audit CSV. Re-run `audit_shares_quality` locally before treating
the sample results as a current quality gate.

| Roadmap item | Status | Evidence and limitation |
| --- | --- | --- |
| Deterministic 200-security EODHD audit | Re-run with corrected PIT metric | The local `artifacts/research/shares_quality_200/summary.json` reported 99.0% recorded HTTP success, 92.5% with any usable source, 88.5% with PIT shares at research start, 98.41% sampled row coverage, and 93.51% filing-date completeness by record. Only 45.0% of securities had filing dates on *all* records. The sample is stratified, not a universe-wide estimate. |
| Permanent Bronze quarterly balance sheets | Loaded | 9,461 universe tickers; 9,437 HTTP 200; 8,754 tickers with usable records; 564,397 source observations and 524,464 usable filing-date-plus-shares observations. Reported coverage: 92.53% of tickers, 93.97% of securities, 98.22% of research rows. Code and tables are in `load_eodhd_fundamentals_balance_sheet.py`. |
| Silver shares PIT by filing date | Built | `create_security_shares_outstanding_pit.sql` applies an ASOF join on `filing_date`, excludes ambiguous ticker identity and flags observations over 365 days old. The post-rebuild reported usable coverage was 97.04% of eligible research rows. This is EODHD issuer-total shares, not class-specific shares. |
| Automatically detect simultaneous listed issues | Candidate layer built | The reported detector output was 22 issuers, 45 issues and 119,032 rows in one audit; a later corrected impact calculation cited 59 securities/tickers, 146,973 rows, or 0.8709% of the strict universe. The SQL itself is explicitly a candidate layer based on overlapping spans and SEC current ticker evidence, not a final issuer/class decision. Reconcile these two denominators before an override. |
| SEC class-specific share observations | Ingested as candidates | 1,098 filings and 6,011 source facts across 22 issuers; 4,461 had a unique same-filing symbol mapping and 1,550 did not. The latter include 1,213 with no symbol evidence, 236 with only later evidence, and 84 with multiple historical symbols. Audit categories and the Wiley transition are diagnostic; no general backward ticker assignment is approved. |
| SEC override for affected listed classes | Built, awaiting local coverage audit | `build_sec_market_cap.py` resolves explicitly mapped SEC shares for simultaneously eligible sibling issues where a filing distinguishes at least two symbols and classes. It uses filing dates, a 365-day age limit, and leaves other class dates without SEC evidence missing. Ordinary single-listed dates retain EODHD PIT shares. Source accession and document hash are retained. This conservative rule may leave many class dates without caps; no backward symbol mapping is inferred. |
| Daily security market cap | Built, awaiting local coverage audit | `silver.security_daily_market_cap` multiplies raw reconciled close by resolved PIT listed-issue shares, preserving missing/ambiguous shares as NULL. The builder prints overall and simultaneous-class coverage; actual local counts are not yet available. |
| Equal- and cap-weighted market/decile returns | Partial | Existing market return and deciles are equal weighted. `silver.research_market_daily_weighted` adds a matched-cohort equal-weight and lagged-cap-weight market series with coverage counts. Cap-weighted forward targets and decile returns are pending the local cap coverage review. |
| Re-run 1/5/10/20/60-day benchmark | Pending | A one-day TabPFN validation run completed on 250,000 sampled rows with one estimator. It is not a five-horizon rerun under both market definitions. The 2025+ test period remains untouched. |

## Corrected quality gate

Run this read-only audit against the loaded local database:

```bash
python -m open_equity_data.audit_shares_quality
```

It selects 20 distinct security IDs from each of ten research-history deciles,
using a stable hash. It uses recorded Bronze HTTP responses, source record
filing dates and actual Silver PIT availability at each security's first
eligible research date. It saves the sampled rows and a summary with failure
concentration by short history, early termination, old research start and low
median dollar volume. Dollar volume is a liquidity proxy, **not** market cap.
No fresh API request is made. The sample is deliberately stratified by history
length, so its unweighted percentages do not estimate universe-wide rates;
the full-load and Silver-row coverage figures above serve that purpose.

The corrected sample has 12/32 short-history securities with no usable source;
the shortest history decile has 55% PIT availability at research start and 55%
row coverage. For 67 securities ending before 2025, 9 have no usable source and
16 lack PIT coverage at research start. No sampled security began before 2011,
so the audit cannot assess that older-history subgroup. The lowest dollar-volume
quartile has 4/50 with no usable source and 6/50 missing at research start.

## Next implementation gate

Run the local overlay and inspect its source and coverage counts:

```bash
python -m open_equity_data.build_sec_market_cap
```

It requires the previously built SEC candidate, multi-issue candidate, EODHD
PIT, universe, return and reconciled price tables. It rebuilds the four new
Silver tables in a transaction and rolls back on duplicate rows, future filings
or issuer-total use on simultaneous-class dates. It also fails if no dated SEC
class observation reaches an eligible issue. The market series uses the
previous session's available cap to weight today's gross total returns and
reports matched equal-weight returns next to cap-weighted returns. It is a
descriptive series; coverage gaps and missing class evidence require review
before deriving alternative model labels, decile returns and five-horizon
benchmark artifacts. Reconcile the two historical candidate issuer counts
against this resolved row-level audit rather than treating candidates as
approved class mappings.
