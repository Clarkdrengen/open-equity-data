# MSCI RIF share evidence: separate from small-cap extension shares

The M15D/M15E extension's `scap_*` fields describe small-cap index shares.
Zero matched extension shares do **not** imply the RIF lacks a security share
count. The 147-field RIF dictionary supplied locally contains
`eod_number_of_shares_today`, `eod_number_of_shares_next_day` and
`closing_number_of_shares`, plus price, price currency and security cap fields.
Three complete rows of the confidential excerpt parsed with positive values
for both Today and Closing shares. The excerpt and source rows are not in Git.

The existing local RIF ZIP bytes remain in the Bronze archive tables. Build
separate Silver observations directly from those retained bytes, with SHA-256
verification, ZIP member and dictionary validation, source digest/line,
raw values, parsed values and status:

```bash
python -m open_equity_data.build_msci_rif_share_candidates --family m15d
python -m open_equity_data.audit_msci_rif_share_candidates --family m15d
```

The optional M15E pass uses `--family m15e` on the same commands. If its RIF
dictionary differs, the Silver transaction fails and the Bronze ZIP remains
unchanged. Already parsed source digests are skipped; `--rebuild` replaces
their derived rows from the exact archived source.

The resulting `silver.msci_m15d_rif_share_observation` (or M15E equivalent)
holds dated source facts, **not** an approved security-level share series.
The overlap audit joins by monthly observation date, MSCI security code and
ISIN to the existing priced-issue candidate, whose price is the latest
eligible business-day price on or before the month-end snapshot within seven
days. It retains per-source share variants, identity/PIT/split blockers and
separate Closing and Today ratios to filed EODHD shares. The month-end
snapshot is not a known publication date. Index methodology, ADR conversion,
share class, corporate actions and cap/price unit interpretation must be
reviewed before use in daily point-in-time market caps or backtests. The
audit makes no changes to canonical shares, market caps or return weights.
