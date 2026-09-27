# Confidential MSCI M15E emerging-market source pilot

The local `*m15e.extension.zip` and `*m15e_rif.zip` families are distinct from
M15D. The first provides dated MSCI security/share evidence; the RIF provides
dated MSCI codes, names, and ISIN. Bronze stores each whole ZIP byte-for-byte
with SHA-256, relative path, member metadata and ingestion time in separate
`bronze.msci_m15e_source_archive` and
`bronze.msci_m15e_rif_source_archive` tables. Existing local files are not
modified or uploaded. Rerunning the importer verifies and skips existing bytes.

Start with three first/middle/last archives from each family:

```bash
python -m open_equity_data.load_msci_m15e_bronze \
  --directory "/Users/nickclark/Dropbox/MSCI Master/history" --pilot
python -m open_equity_data.build_msci_m15e_silver
python -m open_equity_data.load_msci_m15e_rif_bronze \
  --directory "/Users/nickclark/Dropbox/MSCI Master/history" --pilot
python -m open_equity_data.build_msci_m15e_rif_silver
python -m open_equity_data.audit_msci_m15e_name_isin_consistency
python -m open_equity_data.audit_msci_m15e_share_discrepancies
```

The extension parser requires the same 17 named dictionary fields as M15D.
The RIF parser requires dated MSCI codes, name and ISIN; its remaining fields
may vary. If the M15E schema differs, the Silver build fails within a
transaction while the original bytes remain in Bronze. Review the field
dictionary locally before adapting the parser. The pilot has only been tested
with synthetic source-shaped files; actual M15E dictionaries and usefulness
for priced securities have not yet been observed.

After a successful pilot, repeat the two import commands without `--pilot`,
then repeat their Silver builders and audits. Silver output is kept separate:

- `silver.msci_m15e_security_observation` and
  `silver.msci_m15e_rif_observation`: source line and digest, parsed dated
  share/identifier fields and parse status.
- `silver.msci_m15e_identity_candidate` and
  `silver.msci_m15e_price_overlap_candidate`: date/MSCI-code reconciliation,
  ISIN match to an eligible priced project security within seven days, and
  ambiguous identity flags.
- `silver.msci_m15e_share_discrepancy_audit`: separate Today and Closing
  shares compared to local EODHD filing-date PIT shares, with split/identity
  blockers and diagnostic scale bands.

An emerging-market security can have a local listing and an ADR with
different share units and identifiers. Exact ISIN and code/name agreement is
necessary evidence, but it does not establish equal share basis or an approved
security mapping. The audit never applies a correction to canonical shares,
market caps, research returns or weights. Review aggregate overlap and
specific local evidence with Nick before deciding any remediation policy.
