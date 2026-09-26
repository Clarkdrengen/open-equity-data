# Share gap and SEC cover-page candidate audit

Run on the local research DuckDB after pulling the branch with PR #25's
Bronze tables. Neither command changes ticker identity, PIT share values,
market caps, or benchmark inputs.

```bash
python -m open_equity_data.audit_full_universe_shares --top 25
python -m open_equity_data.load_sec_cover_page_share_candidates \
  --cik 0000887733 --cik 0001012019 --cik 0001041657 --cik 0001570585
```

The first command is read-only. Its denominator is the current primary
exchange research PIT-share panel. It reports mutually exclusive implemented
EODHD availability reasons for every security/date row and the largest
security/ticker gaps. `pit_issuer_total_available` describes the current
EODHD panel, not approved issue-specific market cap. Cohorts overlap.
Daily available counts are a feasibility diagnostic, not matched signal
deciles or a performance result.

The second command reads raw filing bytes from `bronze.sec_filing_document`
and adds only **unreviewed** source-derived candidate rows to
`silver.sec_cover_page_share_candidate`. It records accession, filed/as-of
dates, full series and reported class labels, value, Bronze document hash,
parser version, source table and row index, and raw row text. Its separate
`silver.sec_cover_page_share_extraction_audit` records one outcome per
processed filing, including zero candidates and errors. It processes audited
filings where the existing Inline XBRL extractor found zero class facts.
Reruns with the same parser version are idempotent. The parser handles
recognized cover-page row tables and multi-series class matrices; it may
miss other layouts or emit ambiguous rows. Compare its preview against
the source and review failures before any downstream use.

No candidate is assigned a ticker/security, propagated across days, or
merged into the existing PIT shares table. This separation preserves the
domain decision gate for class identity, filing availability, corporate
events, and staleness. Only after reviewing coverage and counterexamples
should a new issue-specific resolver and matched decile analysis be built.
