# Confidential MSCI M15D sources

There are two distinct local ZIP families: `m15d.extension.zip` contains
dated security-level share observations; `m15d_rif.zip` contains dated MSCI
codes, names, and ISINs. Never combine them by filename glob alone or infer
an ISIN from a company name.

The extension-file importer is local-only:

```bash
python -m open_equity_data.load_msci_m15d_bronze \
  --directory "/Users/nickclark/Dropbox/MSCI Master/history"
python -m open_equity_data.build_msci_m15d_silver
python -m open_equity_data.load_msci_m15d_rif_bronze \
  --directory "/Users/nickclark/Dropbox/MSCI Master/history"
python -m open_equity_data.build_msci_m15d_rif_silver
python -m open_equity_data.audit_msci_m15d_name_isin_consistency
python -m open_equity_data.audit_msci_m15d_share_discrepancies
```

`bronze.msci_m15d_source_archive` holds exact ZIP bytes with SHA-256,
relative filename, member metadata and ingestion timestamp. The Silver
builder reads those archived bytes, parses the embedded 17-field dictionary
and pipe-delimited rows, and writes raw and parsed share fields with source
digest and line number to `silver.msci_m15d_security_observation`.
The RIF archive is preserved separately in
`bronze.msci_m15d_rif_source_archive`; its Silver parser reads the embedded
147-field dictionary but stores only the required dated MSCI-code, name and
identifier evidence in `silver.msci_m15d_rif_observation`.

The audit joins on date and MSCI security code, checks issuer and timeseries
code agreement, duplicate share/ISIN conflicts, and normalized name agreement.
`silver.msci_m15d_identity_candidate` retains all extension keys with status;
`silver.msci_m15d_price_overlap_candidate` shows dated ISIN matches to the
project's primary-exchange price universe, including `name_review` cases as
explicitly unapproved candidates. It prints only aggregate counts.

The MSCI security code is not the project's security ID. The `shares_today`
and `closing_shares` fields have index-timing labels, and the file also
includes inclusion factors. No canonical shares or portfolio weights are
changed. Raw ZIPs and row-level outputs stay on the local Mac database,
not GitHub. The pasted RIF excerpt used for local parser validation contained
real names and identifiers and is not included in repository tests or docs.

`silver.msci_m15d_share_discrepancy_audit` retains both MSCI share fields
separately and compares each with EODHD filing-date PIT shares at the matched
price date. Its near-1x, near-1000x and other-ratio bands are **diagnostics**.
It withholds comparable ratios for name/code ambiguity, multiple project
security IDs, unavailable EODHD shares, or a split between the EODHD fiscal
period and comparison date. It retains filing age and inclusion-factor text.
First review the overlap counts and concrete source rows locally, then decide
which error signatures to search for outside MSCI coverage. Do not apply a
general multiplier to uncovered securities based solely on a ratio band.
