# Confidential MSCI M15D sources

There are two distinct local ZIP families: `m15d.extension.zip` contains
dated security-level share observations; `m15d_rif.zip` reportedly contains
ISIN and may provide the exact MSCI-code crosswalk. Never combine them by
filename glob alone or infer an ISIN from a company name.

The extension-file importer is local-only:

```bash
python -m open_equity_data.load_msci_m15d_bronze \
  --directory "/Users/nickclark/Dropbox/MSCI Master/history"
python -m open_equity_data.build_msci_m15d_silver
```

`bronze.msci_m15d_source_archive` holds exact ZIP bytes with SHA-256,
relative filename, member metadata and ingestion timestamp. The Silver
builder reads those archived bytes, parses the embedded 17-field dictionary
and pipe-delimited rows, and writes raw and parsed share fields with source
digest and line number to `silver.msci_m15d_security_observation`.

The present output is **unmapped candidate evidence**. The MSCI security
code is not the project's security ID or ISIN. The `shares_today` and
`closing_shares` fields have index-timing labels, and the file also includes
inclusion factors. No canonical shares or portfolio weights are changed.
After inspecting the RIF schema, join on exact MSCI code and effective date,
audit name and ISIN consistency, and only then measure price-universe overlap.
Raw ZIPs and row-level outputs stay on the local Mac database, not GitHub.
