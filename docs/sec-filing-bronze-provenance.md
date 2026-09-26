# SEC filing source retention

The class-share loader records exact SEC EDGAR primary-document bytes in two
Bronze tables before deriving Silver facts:

- `bronze.sec_filing_document`: immutable document bytes keyed by SHA-256,
  byte count, and first database ingestion time.
- `bronze.sec_filing_document_observation`: accession, CIK, form, filing date,
  primary filename, full SEC archive URL, source system, source access route,
  ingestion time, and the document hash. A changed document is a new version,
  never an overwrite.

`source_access=local_cache` means the document was already in the project's
SEC file cache when ingested; it **does not** assert when the original HTTP
retrieval happened. `sec_archive_download` means this invocation fetched it.
`ingested_at` is the database load time, not the SEC filing date or when the
share observation became known. The exact EDGAR archive URL and content hash
link each Bronze row to its source.

The existing `silver.sec_class_share_candidate` and
`silver.sec_class_share_filing_audit` retain `source_document_sha256`. Their
current extraction still covers only the supported Inline XBRL facts. Bronze
retention does not approve a class-to-security mapping, parse untagged cover
pages, or change the EODHD PIT shares and market-cap outputs.

For an existing database, run once from the repository root:

```bash
python -m open_equity_data.backfill_sec_filing_bronze
```

This is idempotent. It takes its work list from successful Silver SEC filing
audits, uses cached filings where present, downloads missing documents, and
checks bytes against the audit's recorded hash. `HASH MISMATCH` and `ERROR`
rows remain unresolved; no Silver interpretation is changed. Set
`SEC_USER_AGENT` if the cache lacks documents and the SEC must be queried.
Run `python -m open_equity_data.load_sec_class_share_candidates` for new
candidate filings; it retains Bronze before parsing. The Silver tables are
rebuilt per accession only after parsing succeeds.

The historical cover-page extraction method and issue-level PIT mapping
remain methodological decisions for review. After agreement, populate new
Silver observations from Bronze, then rebuild and audit downstream PIT shares,
issue caps, weighted returns, and matched benchmarks.
