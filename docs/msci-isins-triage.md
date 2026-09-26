# External ISIN/name panel triage

The supplied `MSCI_USA.csv` is a monthly panel from October 1998 through
September 2018. Its filename does not establish the constituent universe:
valid ISINs span many countries and each month has roughly 1,350–2,810 rows.
`MktCap` appears numerically consistent with USD millions for familiar US
companies, but the file has no unit, float-adjustment, or source metadata.
Do not treat it as a verified whole-company capitalization without checking
its provenance. It cannot directly validate 2022–2026 market-cap anomalies.

On the local DuckDB machine, run these in order (replace the path):

```bash
python -m open_equity_data.load_msci_usa_bronze --msci-csv "$HOME/Downloads/MSCI_USA.csv"
python -m open_equity_data.build_msci_usa_silver
python -m open_equity_data.audit_msci_isin_reconciliation
```

`bronze.msci_usa_source_file` holds the exact source bytes, SHA-256 digest,
original filename, byte count, ingestion time, and supplied-file provenance.
Its bytes are unchanged, including malformed commas and `NA` rows. Loading
the same bytes again is idempotent. `silver.msci_usa_observation` reconstructs
fields from those Bronze bytes and retains every row with its source digest,
source row number, raw fields, and parse status. The audit reads only Silver
MSCI observations. If several source files are archived, supply the printed
digest as `--source-sha256` to both the Silver builder and audit. It compares
historical names with `bronze.eodhd_symbol_reference` on **exact ISIN** and
reports IDs/tickers from `silver.security_ticker_reference_resolution`.
The outputs are `msci_isin_name_profile.csv`, `invalid_isins.csv`,
`duplicate_date_isin.csv`, and `msci_vs_project_isin_names.csv` under
`artifacts/research/msci_isin_reconciliation`. Use `--profile-only` if the
reference tables are unavailable in a database that has the MSCI Bronze and
Silver tables.

Unquoted commas in 78 company names are reconstructed from the first three
and last CSV fields. Rows with `NA` padding, blank/invalid ISINs, and duplicate
date–ISIN observations are counted separately; neither an invalid identifier
nor a duplicate cap is silently approved. A normalized text match is merely a
name diagnostic. Corporate renames can share one valid ISIN. Multiple
security IDs can be episodes of one issue. A different ISIN may distinguish
an ADR from ordinary shares of the same issuer, so matching issuer names
cannot justify assigning an issuer share count to the ADR. The MSCI file is
historical validation evidence only. Its supplied cap figures are never used
to overwrite market caps or approve share counts; any adjustment would be an
explicit Silver derivation with source lineage, with Gold optional.
