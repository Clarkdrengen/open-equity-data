# MSCI market-cap implied shares: diagnostic candidate

The historical `MSCI_USA.csv` has security-level ISIN, date, and a cap value.
The separate `_m51d.zip` files examined by field dictionary describe index
statistics and are not needed for the issue-level calculation.

After the CSV has been archived in Bronze and parsed into
`silver.msci_usa_observation`, run:

```bash
python -m open_equity_data.build_msci_implied_shares_candidate
```

If several CSV versions exist, pass `--source-sha256` with the archived file
digest. The command creates only two Silver candidate tables:

- `silver.msci_implied_shares_candidate`: one source date/ISIN matched to a
  primary-exchange issue and its last price no more than seven calendar days
  earlier. Exact source duplicate caps are represented once; conflicting
  date/ISIN cap values and matches to multiple security IDs are flagged and
  yield no implied share value.
- `silver.msci_implied_shares_scale_audit`: compares the implied value to the
  locally available EODHD filing-date PIT share observation at the price
  date. It flags ratios near 1,000, 0.001, 1, or elsewhere, retaining source
  dates, age, and identity diagnostics. Non-comparable rows have no ratio.

The illustrative calculation is
`mktcap_as_supplied * 1,000,000 / raw_close`, **conditional on** the cap
being USD millions and the issue price being USD. Neither the CSV's unit nor
whether it contains full or float-adjusted cap is established. A ratio can
also reflect a split between the filed EODHD share count and price date,
issuer totals applied to a class, corporate actions, or identity errors.
The source observation date is not a proven release date, so these values
are not automatically point-in-time tradable. Do not replace canonical shares,
fill future historical periods, or rebuild cap-weighted returns from this
candidate without reviewing these issues and agreeing a Silver policy.
