"""Read-only security-level audit of EODHD PIT-share gaps.

The output is diagnostic: an issuer balance-sheet total is not approved
class-specific shares for an individual listed issue.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

from open_equity_data.db import connect


ISSUE_SQL = """
WITH source AS (
    SELECT ticker, MIN(filing_date) AS first_filing
    FROM silver.security_shares_outstanding_effective
    GROUP BY ticker
),
request AS (
    SELECT ticker,
           COUNT(*) AS attempts,
           COUNT(*) FILTER (WHERE http_status = 200) AS http_200,
           COUNT(*) FILTER (WHERE usable_record_count > 0) AS usable
    FROM bronze.eodhd_fundamental_balance_sheet_request
    GROUP BY ticker
),
classified AS (
    SELECT p.security_id, p.ticker, p.date,
           CASE
             WHEN p.shares_pit_available THEN 'pit_issuer_total_available'
             WHEN p.shares_outstanding IS NULL AND s.first_filing IS NOT NULL
                  AND p.date < s.first_filing THEN 'before_first_filing'
             WHEN p.shares_outstanding IS NULL AND s.first_filing IS NULL
                  AND COALESCE(r.attempts, 0) = 0 THEN 'no_eodhd_request'
             WHEN p.shares_outstanding IS NULL AND s.first_filing IS NULL
                  AND COALESCE(r.http_200, 0) = 0 THEN 'no_successful_response'
             WHEN p.shares_outstanding IS NULL AND s.first_filing IS NULL
                  THEN 'response_without_usable_filed_shares'
             WHEN p.ticker_identity_ambiguous THEN 'ticker_identity_ambiguous'
             WHEN p.shares_age_days > 365 THEN 'older_than_365_days'
             ELSE 'other_unavailable'
           END AS reason
    FROM silver.security_daily_shares_outstanding_pit p
    LEFT JOIN source s ON s.ticker = p.ticker
    LEFT JOIN request r ON r.ticker = p.ticker
)
SELECT security_id, ticker, reason, COUNT(*) AS rows,
       MIN(date) AS first_date, MAX(date) AS last_date
FROM classified
GROUP BY security_id, ticker, reason
ORDER BY security_id, ticker, reason
"""


DATE_SQL = """
SELECT date, COUNT(*) AS rows,
       COUNT(*) FILTER (WHERE shares_pit_available) AS available
FROM silver.security_daily_shares_outstanding_pit
GROUP BY date ORDER BY date
"""


def audit(con, *, top: int = 25) -> dict:
    by_reason = Counter()
    issues: dict[tuple[int, str], dict] = defaultdict(
        lambda: {"rows": 0, "gap_rows": 0, "first": None,
                 "last": None, "reasons": Counter()}
    )
    for security_id, ticker, reason, rows, first, last in con.execute(ISSUE_SQL).fetchall():
        rows = int(rows)
        by_reason[reason] += rows
        item = issues[(security_id, ticker)]
        item["rows"] += rows
        item["reasons"][reason] += rows
        if reason != "pit_issuer_total_available":
            item["gap_rows"] += rows
        item["first"] = min(item["first"], first) if item["first"] else first
        item["last"] = max(item["last"], last) if item["last"] else last

    cohorts = defaultdict(lambda: {"issues": 0, "rows": 0, "gap_rows": 0})
    for item in issues.values():
        labels = ["short_history_at_most_252_rows"] if item["rows"] <= 252 else []
        if item["last"].year < 2025:
            labels.append("ended_before_2025")
        if item["first"].year < 2011:
            labels.append("start_before_2011")
        for label in labels:
            cohorts[label]["issues"] += 1
            cohorts[label]["rows"] += item["rows"]
            cohorts[label]["gap_rows"] += item["gap_rows"]

    daily = con.execute(DATE_SQL).fetchall()
    total = sum(by_reason.values())
    gap = total - by_reason["pit_issuer_total_available"]
    worst = sorted(issues.items(), key=lambda pair: (-pair[1]["gap_rows"], pair[0]))[:top]
    return {
        "scope": "current primary-exchange research PIT-share rows",
        "rows": total,
        "issues": len(issues),
        "unavailable_rows": gap,
        "by_reason": dict(sorted(by_reason.items())),
        "cohorts_overlap": dict(sorted(cohorts.items())),
        "dates": len(daily),
        "dates_with_fewer_than_10_available_issues": sum(n < 10 for _, _, n in daily),
        "worst_daily_available_fraction": min((n / rows for _, rows, n in daily), default=None),
        "top_issue_gaps": [
            {"security_id": key[0], "ticker": key[1],
             "first": str(item["first"]), "last": str(item["last"]),
             "rows": item["rows"], "gap_rows": item["gap_rows"],
             "reasons": dict(item["reasons"])}
            for key, item in worst
        ],
        "notes": [
            "Reasons classify the implemented EODHD PIT panel, not verified issue-level market caps.",
            "A ticker can have several security IDs; first filing is ticker-level diagnostic evidence.",
            "Cohorts overlap. Daily availability is a baseline, not a signal-decile backtest.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()
    with connect(read_only=True) as con:
        result = audit(con, top=args.top)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
