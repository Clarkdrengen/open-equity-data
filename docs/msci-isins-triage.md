# External ISIN/name panel triage

The supplied `MSCI_USA.csv` is a monthly panel from October 1998 through
September 2018. Its filename does not establish the constituent universe:
valid ISINs span many countries and each month has roughly 1,350–2,810 rows.
`MktCap` appears numerically consistent with USD millions for familiar US
companies, but the file has no unit, float-adjustment, or source metadata.
Do not treat it as a verified whole-company capitalization without checking
its provenance. It cannot directly validate 2022–2026 market-cap anomalies.

Run `python -m open_equity_data.audit_msci_isin_reconciliation --msci-csv
/path/to/MSCI_USA.csv` from the repository on the local DuckDB machine.
It reads the external file without loading it into Bronze or Silver and
compares its historical names with `bronze.eodhd_symbol_reference` names
on **exact ISIN**. It also reports the security IDs/tickers associated with
that ISIN in `silver.security_ticker_reference_resolution`.
The outputs are `msci_isin_name_profile.csv`, `invalid_isins.csv`,
`duplicate_date_isin.csv`, and `msci_vs_project_isin_names.csv` under
`artifacts/research/msci_isin_reconciliation`. Use `--profile-only` when
the DuckDB database is unavailable.

Unquoted commas in 78 company names are reconstructed from the first three
and last CSV fields. Rows with `NA` padding, blank/invalid ISINs, and duplicate
date–ISIN observations are counted separately; neither an invalid identifier
nor a duplicate cap is silently approved. A normalized text match is merely a
name diagnostic. Corporate renames can share one valid ISIN. Multiple
security IDs can be episodes of one issue. A different ISIN may distinguish
an ADR from ordinary shares of the same issuer, so matching issuer names
cannot justify assigning an issuer share count to the ADR.
