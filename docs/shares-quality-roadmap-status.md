# Shares and market-cap data quality: status after September 25, 2026

The figures below are from terminal results shared in the project conversation.
The repository contains the loaders and audits, but not Nick's local DuckDB or
the original audit CSV. Re-run `audit_shares_quality` locally before treating
the sample results as a current quality gate.

| Roadmap item | Status | Evidence and limitation |
| --- | --- | --- |
| Deterministic 200-security EODHD audit | Run | 97.0% HTTP 200; 88.0% had any PIT-usable shares; 90.0% reported research-start coverage. The old start metric compared fiscal period dates, not actual filing-date-based availability. All-record filing-date completeness was 50.0%; this is a stricter measure than any usable record. Failures were reported as concentrated in older, short-lived and awkward names, without a subgroup table preserved in Git. |
| Permanent Bronze quarterly balance sheets | Loaded | 9,461 universe tickers; 9,437 HTTP 200; 8,754 tickers with usable records; 564,397 source observations and 524,464 usable filing-date-plus-shares observations. Reported coverage: 92.53% of tickers, 93.97% of securities, 98.22% of research rows. Code and tables are in `load_eodhd_fundamentals_balance_sheet.py`. |
| Silver shares PIT by filing date | Built | `create_security_shares_outstanding_pit.sql` applies an ASOF join on `filing_date`, excludes ambiguous ticker identity and flags observations over 365 days old. The post-rebuild reported usable coverage was 97.04% of eligible research rows. This is EODHD issuer-total shares, not class-specific shares. |
| Automatically detect simultaneous listed issues | Candidate layer built | The reported detector output was 22 issuers, 45 issues and 119,032 rows in one audit; a later corrected impact calculation cited 59 securities/tickers, 146,973 rows, or 0.8709% of the strict universe. The SQL itself is explicitly a candidate layer based on overlapping spans and SEC current ticker evidence, not a final issuer/class decision. Reconcile these two denominators before an override. |
| SEC class-specific share observations | Ingested as candidates | 1,098 filings and 6,011 source facts across 22 issuers; 4,461 had a unique same-filing symbol mapping and 1,550 did not. The latter include 1,213 with no symbol evidence, 236 with only later evidence, and 84 with multiple historical symbols. Audit categories and the Wiley transition are diagnostic; no general backward ticker assignment is approved. |
| SEC override for affected listed classes | Pending | There is no resolved security-level PIT overlay table or rule that replaces issuer totals only during verified simultaneous-class intervals. |
| Daily security market cap | Pending | No final close-times-resolved-class-shares table, coverage report, or stale-share gate. |
| Equal- and cap-weighted market/decile returns | Partial | Existing market return and deciles are equal weighted. There is no cap-weighted counterpart, and benchmark targets still use the equal-weight market return. |
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

## Next implementation gate

Reconcile the candidate issuer denominator and approve class-to-security
resolutions only from dated, auditable evidence. Then build the SEC overlay
with explicit fallback to EODHD totals for ordinary single-listed issuers,
source and freshness columns on every daily share count, and a coverage audit
before deriving daily market cap. Keep separate equal- and cap-weighted
benchmark artifacts and compare on matched eligible dates/securities.
