"""Read-only impact audit for candidate issue-level shares resolution.

Prints JSON to stdout. It neither fetches sources nor approves a historical
CIK, class-to-security mapping, SEC fact, or market-cap observation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

from open_equity_data.db import connect


SPAN_SQL = """
SELECT COUNT(*) AS pairs, COUNT(DISTINCT cik) AS candidate_ciks,
       (SELECT COUNT(DISTINCT security_id)
        FROM (
            SELECT security_id_a AS security_id
            FROM silver.multi_listed_common_equity_candidate
            UNION ALL
            SELECT security_id_b
            FROM silver.multi_listed_common_equity_candidate
        ) issues) AS distinct_issues
FROM silver.multi_listed_common_equity_candidate
"""


IMPACT_SQL = """
WITH directional_pairs AS MATERIALIZED (
    SELECT cik, security_id_a AS security_id, security_id_b AS sibling_id,
           overlap_start, overlap_end
    FROM silver.multi_listed_common_equity_candidate
    UNION ALL
    SELECT cik, security_id_b, security_id_a, overlap_start, overlap_end
    FROM silver.multi_listed_common_equity_candidate
),
sec_first AS (
    SELECT cik, UPPER(trading_symbol) AS ticker,
           MIN(filing_date) AS first_mapped_filing
    FROM silver.sec_class_share_candidate
    WHERE symbol_mapping_status = 'mapped_unique_symbol'
      AND trading_symbol IS NOT NULL
    GROUP BY cik, UPPER(trading_symbol)
),
candidate_days AS MATERIALIZED (
    SELECT p.security_id, p.date,
           STRING_AGG(DISTINCT d.cik, ',' ORDER BY d.cik) AS candidate_ciks,
           COUNT(DISTINCT d.cik) AS candidate_cik_count,
           BOOL_OR(sibling.security_id IS NOT NULL) AS coobserved_sibling,
           BOOL_OR(f.first_mapped_filing <= p.date) AS mapped_fact_filed,
           BOOL_OR(f.first_mapped_filing > p.date) AS later_mapped_fact,
           BOOL_OR(f.first_mapped_filing IS NOT NULL) AS any_mapped_fact
    FROM silver.security_daily_shares_outstanding_pit p
    JOIN directional_pairs d
      ON d.security_id = p.security_id
     AND p.date BETWEEN d.overlap_start AND d.overlap_end
    LEFT JOIN silver.research_universe_eligibility sibling
      ON sibling.security_id = d.sibling_id
     AND sibling.date = p.date
     AND sibling.primary_research_eligible_exchange
    LEFT JOIN sec_first f ON f.cik = d.cik AND f.ticker = UPPER(p.ticker)
    GROUP BY p.security_id, p.date
),
classified AS (
    SELECT p.security_id, p.ticker, p.date,
           CASE
             WHEN c.coobserved_sibling THEN 'coobserved_multi_issue_candidate'
             WHEN c.security_id IS NOT NULL THEN 'span_only_multi_issue_candidate'
             WHEN p.ticker_identity_ambiguous THEN 'ticker_identity_ambiguous'
             WHEN p.shares_pit_available THEN 'eodhd_pit_other_issue_days'
             ELSE 'eodhd_unavailable_other_issue_days'
           END AS partition,
           CASE
             WHEN p.shares_pit_available THEN 'available'
             WHEN p.shares_outstanding IS NULL THEN 'missing'
             WHEN p.ticker_identity_ambiguous THEN 'ticker_identity_ambiguous'
             WHEN p.shares_age_days > 365 THEN 'older_than_365_days'
             ELSE 'other_unavailable'
           END AS eodhd_pit_status,
           CASE
             WHEN c.security_id IS NULL THEN 'outside_detector'
             WHEN c.mapped_fact_filed THEN 'mapped_candidate_fact_filed'
             WHEN c.later_mapped_fact THEN 'later_mapped_candidate_fact_only'
             WHEN c.any_mapped_fact THEN 'mapped_candidate_fact_unavailable'
             ELSE 'no_mapped_candidate_fact'
           END AS sec_candidate_status,
           COALESCE(c.candidate_ciks, '') AS candidate_ciks,
           COALESCE(c.candidate_cik_count, 0) AS candidate_cik_count
    FROM silver.security_daily_shares_outstanding_pit p
    LEFT JOIN candidate_days c
      ON c.security_id = p.security_id AND c.date = p.date
)
SELECT security_id, ticker, partition, eodhd_pit_status,
       sec_candidate_status, candidate_ciks, candidate_cik_count,
       COUNT(*) AS issue_days, MIN(date) AS first_date, MAX(date) AS last_date
FROM classified
GROUP BY security_id, ticker, partition, eodhd_pit_status,
         sec_candidate_status, candidate_ciks, candidate_cik_count
ORDER BY security_id, ticker, partition, eodhd_pit_status,
         sec_candidate_status, candidate_ciks
"""


def audit(con, *, top: int = 20) -> dict:
    pairs, candidate_ciks, distinct_issues = con.execute(SPAN_SQL).fetchone()
    partitions = Counter()
    eodhd = Counter()
    sec = Counter()
    cross_tab = Counter()
    by_candidate_cik = Counter()
    issue_totals = defaultdict(lambda: {"issue_days": 0, "candidate_days": 0,
                                        "coobserved_days": 0, "eodhd_unavailable": 0,
                                        "mapped_candidate_fact_filed_days": 0,
                                        "candidate_ciks": set()})
    multiple_cik_days = 0
    for (security_id, ticker, partition, eodhd_status, sec_status, ciks,
         cik_count, days, _first, _last) in con.execute(IMPACT_SQL).fetchall():
        days = int(days)
        partitions[partition] += days
        eodhd[eodhd_status] += days
        if ciks:
            sec[sec_status] += days
            cross_tab[(partition, eodhd_status, sec_status)] += days
            for cik in ciks.split(','):
                by_candidate_cik[cik] += days
        if cik_count > 1:
            multiple_cik_days += days
        item = issue_totals[(security_id, ticker)]
        item["issue_days"] += days
        if ciks:
            item["candidate_days"] += days
            item["candidate_ciks"].update(ciks.split(','))
        if partition == "coobserved_multi_issue_candidate":
            item["coobserved_days"] += days
        if eodhd_status != "available":
            item["eodhd_unavailable"] += days
        if ciks and sec_status == "mapped_candidate_fact_filed":
            item["mapped_candidate_fact_filed_days"] += days

    total = sum(partitions.values())
    if not total:
        raise RuntimeError("No PIT issue-days found; check the selected database")
    candidates = sorted(
        ((key, val) for key, val in issue_totals.items() if val["candidate_days"]),
        key=lambda pair: (-pair[1]["candidate_days"], pair[0]),
    )[:top]
    gaps = sorted(
        issue_totals.items(),
        key=lambda pair: (-pair[1]["eodhd_unavailable"], pair[0]),
    )[:top]

    def issue_record(key, value):
        return {"security_id": key[0], "ticker": key[1],
                **{k: v for k, v in value.items() if k != "candidate_ciks"},
                "candidate_ciks": sorted(value["candidate_ciks"])}

    return {
        "scope": "current primary-exchange research PIT issue-days",
        "issue_days": total,
        "distinct_security_ticker_pairs": len(issue_totals),
        "detector_span_pairs": int(pairs),
        "detector_candidate_ciks": int(candidate_ciks),
        "detector_distinct_issues": int(distinct_issues),
        "exclusive_partitions": dict(sorted(partitions.items())),
        "eodhd_pit_status_all_partitions": dict(sorted(eodhd.items())),
        "candidate_days_by_sec_evidence": dict(sorted(sec.items())),
        "candidate_cross_tab": [
            {"partition": partition, "eodhd_pit_status": eodhd_status,
             "sec_candidate_status": sec_status, "issue_days": days}
            for (partition, eodhd_status, sec_status), days
            in sorted(cross_tab.items())
        ],
        "candidate_cik_issue_days": dict(sorted(by_candidate_cik.items())),
        "candidate_days_with_multiple_possible_ciks": multiple_cik_days,
        "top_candidate_issues": [issue_record(k, v) for k, v in candidates],
        "top_eodhd_gap_issues": [issue_record(k, v) for k, v in gaps],
        "notes": [
            "Partitions are mutually exclusive and sum to issue_days; evidence/status cuts overlap them.",
            "The detector uses current SEC ticker/CIK evidence and issue-date spans, not dated legal identity proof.",
            "Coobserved means both issues have eligible rows on the same date; span-only does not prove a sibling traded that day.",
            "A mapped SEC candidate fact merely has a unique symbol in its own filing and a filing date no later than the research date.",
            "No class-to-security resolution, SEC carry-forward, or issue market cap is approved by this audit.",
            "Candidate CIK totals can double-count an issue-day when more than one possible CIK is attached.",
            "Outside the detector does not establish that an EODHD issuer total is safe for an issue.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    with connect(read_only=True) as con:
        result = audit(con, top=args.top)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
