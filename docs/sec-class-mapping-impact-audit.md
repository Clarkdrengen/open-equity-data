# SEC class mapping impact audit

Run against the loaded local DuckDB:

```bash
python -m open_equity_data.audit_sec_class_mapping_impact
```

The command opens the database read-only and writes CSV/JSON reports under
`artifacts/research/sec_class_mapping_impact/`. It does not build or change
Silver tables, approve class mappings, apply an observation age limit, or use
the proposed overlay in PR #23.

| File | Contents |
| --- | --- |
| `summary.json` | Candidate issue-date counts, evidence statuses, age bands, filing processing statuses and unmapped fact status counts. |
| `issuers.csv` | Counts by candidate CIK across simultaneous eligible listed issues. |
| `issues.csv` | Counts and evidence-date range by candidate CIK, security ID and ticker. |
| `missing_spans.csv` | Consecutive research-session spans with no same-filing symbol fact filed by that date, by candidate issue and reason. |
| `unmapped_members.csv` | Source fact counts by issuer, XBRL class member, diagnostic evidence status and possible symbol. Possible symbols are **not** approved. |
| `candidate_issue_days.csv` | Individual simultaneous candidate issue dates, latest mapped filing and its age, evidence status, and separate EODHD PIT availability flag. |

The statuses mean:

- `no_same_filing_symbol_fact_for_ticker`: no extracted mapped share fact for
  that candidate CIK/ticker in the loaded filing set;
- `before_first_mapped_filing`: a mapped fact exists later, but none was filed
  by this research date;
- `mapped_fact_filed_by_date`: a same-filing class/symbol fact was filed by
  this date; this says nothing about how old or otherwise usable that fact is;
- `multiple_candidate_ciks`: the same security/date has more than one
  candidate issuer CIK, and is flagged for identity review.

The candidate CIK/ticker association comes from current SEC ticker evidence
and is not an approved historical identity mapping. Missing metadata in the
extractor may reflect an omitted filing tag, an unsupported tag layout, or a
class without a listed symbol. The audit cannot distinguish those causes
without filing-level review. Fact counts do not measure security-day coverage.
