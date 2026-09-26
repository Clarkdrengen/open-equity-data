"""Read-only impact audit of candidate SEC class-share mappings.

The report counts same-day eligible sibling issue dates and checks whether a
same-filing class/symbol share fact had been filed by each date. It never
assigns shares, approves a candidate CIK/security link, or applies an age gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pandas as pd

from open_equity_data.audit_sec_class_share_mapping import Candidate, classify_unmapped
from open_equity_data.db import connect


DEFAULT_OUTPUT = Path("artifacts/research/sec_class_mapping_impact")

DAILY_SQL = """
WITH paired AS (
    SELECT p.cik, a.security_id, a.date, UPPER(a.ticker) AS ticker
    FROM silver.multi_listed_common_equity_candidate p
    JOIN silver.research_universe_eligibility a
      ON a.security_id = p.security_id_a AND UPPER(a.ticker) = UPPER(p.ticker_a)
     AND a.date BETWEEN p.overlap_start AND p.overlap_end
     AND a.primary_research_eligible_exchange
    JOIN silver.research_universe_eligibility b
      ON b.security_id = p.security_id_b AND UPPER(b.ticker) = UPPER(p.ticker_b)
     AND b.date = a.date AND b.primary_research_eligible_exchange
    UNION
    SELECT p.cik, b.security_id, b.date, UPPER(b.ticker) AS ticker
    FROM silver.multi_listed_common_equity_candidate p
    JOIN silver.research_universe_eligibility b
      ON b.security_id = p.security_id_b AND UPPER(b.ticker) = UPPER(p.ticker_b)
     AND b.date BETWEEN p.overlap_start AND p.overlap_end
     AND b.primary_research_eligible_exchange
    JOIN silver.research_universe_eligibility a
      ON a.security_id = p.security_id_a AND UPPER(a.ticker) = UPPER(p.ticker_a)
     AND a.date = b.date AND a.primary_research_eligible_exchange
),
days AS (
    SELECT DISTINCT cik, security_id, date, ticker FROM paired
),
mapped AS (
    SELECT cik, UPPER(trading_symbol) AS ticker, filing_date,
           COUNT(*) AS mapped_source_facts,
           COUNT(DISTINCT class_member) AS distinct_members,
           COUNT(DISTINCT shares_outstanding) AS distinct_share_values,
           STRING_AGG(DISTINCT accession_number, ',') AS accessions,
           STRING_AGG(DISTINCT class_member, ',') AS class_members,
           COUNT(*) FILTER (WHERE shares_as_of_date IS NULL
                             OR shares_as_of_date > filing_date
                             OR shares_outstanding <= 0) AS invalid_fact_dates_or_values
    FROM silver.sec_class_share_candidate
    WHERE symbol_mapping_status = 'mapped_unique_symbol'
      AND trading_symbol IS NOT NULL
    GROUP BY cik, UPPER(trading_symbol), filing_date
),
history AS (
    SELECT cik, ticker, COUNT(*) AS mapped_filing_dates,
           SUM(mapped_source_facts) AS mapped_source_facts,
           MIN(filing_date) AS first_mapped_filing,
           MAX(filing_date) AS last_mapped_filing
    FROM mapped GROUP BY cik, ticker
),
asof_map AS (
    SELECT d.*, m.filing_date AS latest_mapped_filing,
           m.mapped_source_facts AS latest_filing_fact_count,
           m.distinct_members AS latest_filing_member_count,
           m.distinct_share_values AS latest_filing_share_value_count,
           m.accessions AS latest_filing_accessions,
           m.class_members AS latest_filing_class_members,
           m.invalid_fact_dates_or_values AS latest_filing_invalid_count
    FROM days d
    ASOF LEFT JOIN mapped m
      ON d.cik = m.cik AND d.ticker = m.ticker AND d.date >= m.filing_date
),
cik_conflicts AS (
    SELECT security_id, date, COUNT(DISTINCT cik) AS candidate_ciks
    FROM days GROUP BY security_id, date
)
SELECT a.*, h.mapped_filing_dates, h.mapped_source_facts,
       h.first_mapped_filing, h.last_mapped_filing,
       DATE_DIFF('day', a.latest_mapped_filing, a.date) AS latest_filing_age_days,
       c.candidate_ciks,
       COALESCE(e.shares_pit_available, FALSE) AS eodhd_pit_available
FROM asof_map a
LEFT JOIN history h ON h.cik = a.cik AND h.ticker = a.ticker
LEFT JOIN cik_conflicts c ON c.security_id = a.security_id AND c.date = a.date
LEFT JOIN silver.security_daily_shares_outstanding_pit e
  ON e.security_id = a.security_id AND e.date = a.date
ORDER BY a.cik, a.security_id, a.ticker, a.date
"""


def audit(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    daily = con.execute(DAILY_SQL).df()
    if daily.duplicated(["cik", "security_id", "ticker", "date"]).any():
        raise RuntimeError("Candidate issue/date rows are not unique")
    daily["evidence_status"] = "mapped_fact_filed_by_date"
    daily.loc[daily["latest_mapped_filing"].isna(), "evidence_status"] = (
        "before_first_mapped_filing"
    )
    daily.loc[daily["mapped_filing_dates"].isna(), "evidence_status"] = (
        "no_same_filing_symbol_fact_for_ticker"
    )
    daily.loc[daily["candidate_ciks"] > 1, "evidence_status"] = (
        "multiple_candidate_ciks"
    )

    rows = [Candidate(*row) for row in con.execute("""
        SELECT cik, entity_name, class_member, filing_date, accession_number,
               shares_as_of_date, trading_symbol, symbol_mapping_status
        FROM silver.sec_class_share_candidate
        WHERE symbol_mapping_status IN ('mapped_unique_symbol', 'no_trading_symbol')
        ORDER BY cik, class_member, filing_date, accession_number
    """).fetchall()]
    groups = defaultdict(list)
    for fact, status, possible_symbol in classify_unmapped(rows):
        groups[(fact.cik, fact.entity_name, fact.class_member, status,
                possible_symbol)].append(fact)
    unmapped = pd.DataFrame([
        {
            "cik": cik, "issuer": issuer, "class_member": member,
            "evidence_status": status, "possible_symbol_diagnostic_only": symbol,
            "source_facts": len(facts),
            "first_filing": min(f.filing_date for f in facts),
            "last_filing": max(f.filing_date for f in facts),
        }
        for (cik, issuer, member, status, symbol), facts in groups.items()
    ], columns=["cik", "issuer", "class_member", "evidence_status",
                "possible_symbol_diagnostic_only", "source_facts",
                "first_filing", "last_filing"])
    if not unmapped.empty:
        unmapped = unmapped.sort_values(
            ["source_facts", "cik", "class_member"], ascending=[False, True, True]
        )
    filing_status = dict(con.execute("""
        SELECT processing_status, COUNT(*)
        FROM silver.sec_class_share_filing_audit GROUP BY 1
    """).fetchall())
    mapping_status = dict(con.execute("""
        SELECT symbol_mapping_status, COUNT(*)
        FROM silver.sec_class_share_candidate GROUP BY 1
    """).fetchall())
    summary = {
        "candidate_issue_date_rows": len(daily),
        "candidate_issuers": int(daily["cik"].nunique()),
        "candidate_security_ids": int(daily["security_id"].nunique()),
        "daily_evidence_status_rows": {
            str(k): int(v) for k, v in daily["evidence_status"].value_counts().items()
        },
        "mapped_fact_age_over_365_days_rows": int(
            (daily["latest_filing_age_days"] > 365).sum()
        ),
        "mapped_fact_age_121_to_365_days_rows": int(
            daily["latest_filing_age_days"].between(121, 365).sum()
        ),
        "eodhd_pit_available_on_candidate_rows": int(
            daily["eodhd_pit_available"].sum()
        ),
        "unmapped_source_fact_status": {
            str(k): int(v) for k, v in Counter(
                status for _, status, _ in classify_unmapped(rows)
            ).items()
        },
        "filing_processing_status": filing_status,
        "all_source_fact_mapping_status": mapping_status,
        "notes": [
            "Current ticker-to-CIK links are candidate identity evidence, not approved historical mappings.",
            "A mapped fact filed by date is diagnostic; no shares, freshness, or trading rule is applied.",
            "Fact counts do not equal distinct securities or research days.",
            "Possible symbols for unmapped facts are diagnostic only.",
        ],
    }
    return daily, unmapped, summary


def issue_summary(daily: pd.DataFrame) -> pd.DataFrame:
    result = daily.groupby(["cik", "security_id", "ticker"], dropna=False).agg(
        candidate_days=("date", "size"),
        first_candidate_day=("date", "min"),
        last_candidate_day=("date", "max"),
        days_with_prior_mapped_fact=(
            "evidence_status", lambda x: int((x == "mapped_fact_filed_by_date").sum())
        ),
        first_mapped_filing=("first_mapped_filing", "min"),
        last_mapped_filing=("last_mapped_filing", "max"),
        mapped_source_facts=("mapped_source_facts", "max"),
        eodhd_pit_days=("eodhd_pit_available", "sum"),
        candidate_cik_conflict_days=(
            "candidate_ciks", lambda x: int((x > 1).sum())
        ),
    ).reset_index().sort_values(["cik", "security_id", "ticker"])
    counts = pd.crosstab(
        [daily["cik"], daily["security_id"], daily["ticker"]],
        daily["evidence_status"],
    ).add_prefix("days_").reset_index()
    return result.merge(counts, on=["cik", "security_id", "ticker"])


def issuer_summary(daily: pd.DataFrame) -> pd.DataFrame:
    issues = issue_summary(daily)
    status_columns = [
        c for c in issues if c.startswith("days_")
        and c != "days_with_prior_mapped_fact"
    ]
    summary = issues.groupby("cik").agg(
        candidate_issues=("security_id", "nunique"),
        candidate_issue_days=("candidate_days", "sum"),
        first_candidate_day=("first_candidate_day", "min"),
        last_candidate_day=("last_candidate_day", "max"),
        days_with_prior_mapped_fact=("days_with_prior_mapped_fact", "sum"),
        eodhd_pit_issue_days=("eodhd_pit_days", "sum"),
        candidate_cik_conflict_issue_days=("candidate_cik_conflict_days", "sum"),
    )
    return summary.join(issues.groupby("cik")[status_columns].sum()).reset_index()


def missing_spans(daily: pd.DataFrame) -> pd.DataFrame:
    x = daily.loc[daily["evidence_status"] != "mapped_fact_filed_by_date"].copy()
    # Count missing dates, not calendar days; any intervening covered date
    # splits the span. Keep distinct candidate CIKs separate.
    x["position"] = daily.groupby(["cik", "security_id", "ticker"]).cumcount().loc[x.index]
    x["missing_position"] = x.groupby(
        ["cik", "security_id", "ticker", "evidence_status"]
    ).cumcount()
    x["span_key"] = x["position"] - x["missing_position"]
    return x.groupby(
        ["cik", "security_id", "ticker", "evidence_status", "span_key"]
    ).agg(first_date=("date", "min"), last_date=("date", "max"),
          candidate_days=("date", "size")).reset_index().drop(columns="span_key")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with connect(read_only=True) as con:
        daily, unmapped, summary = audit(con)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(args.output_dir / "candidate_issue_days.csv", index=False)
    issue_summary(daily).to_csv(args.output_dir / "issues.csv", index=False)
    issuer_summary(daily).to_csv(args.output_dir / "issuers.csv", index=False)
    missing_spans(daily).to_csv(args.output_dir / "missing_spans.csv", index=False)
    unmapped.to_csv(args.output_dir / "unmapped_members.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Saved reports in {args.output_dir}")


if __name__ == "__main__":
    main()
