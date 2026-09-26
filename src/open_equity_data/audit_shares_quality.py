"""Deterministic 200-security, read-only audit of loaded shares data.

The original online audit compared the earliest fiscal period to the research
start. This audit checks actual filing-date-based Silver coverage on that date.
It uses recorded Bronze responses and makes no API calls.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from open_equity_data.db import connect


DEFAULT_OUTPUT = Path("artifacts/research/shares_quality_200")

AUDIT_SQL = """
WITH history AS (
    SELECT security_id, MIN(date) AS first_date, MAX(date) AS last_date,
           COUNT(*) AS research_rows
    FROM silver.research_universe_eligibility
    WHERE primary_research_eligible_exchange
    GROUP BY security_id
),
ranked AS (
    SELECT *, NTILE(10) OVER (ORDER BY research_rows, security_id) AS history_decile
    FROM history
),
sample AS MATERIALIZED (
    SELECT * FROM ranked
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY history_decile
        ORDER BY MD5(CAST(security_id AS VARCHAR) || '|shares-quality-v2'), security_id
    ) <= 20
),
security_tickers AS (
    SELECT DISTINCT s.security_id, u.ticker
    FROM sample s
    JOIN silver.research_universe_eligibility u USING (security_id)
    WHERE u.primary_research_eligible_exchange
),
request_by_ticker AS (
    SELECT ticker, COUNT(*) AS requests,
           BOOL_OR(http_status = 200) AS http_success
    FROM bronze.eodhd_fundamental_balance_sheet_request
    GROUP BY ticker
),
observation_by_ticker AS (
    SELECT ticker, COUNT(*) AS source_records,
           COUNT(*) FILTER (WHERE filing_date IS NOT NULL) AS filed_records,
           COUNT(*) FILTER (
               WHERE filing_date IS NOT NULL
                 AND common_stock_shares_outstanding > 0
                 AND period_date <= filing_date
           ) AS usable_records
    FROM bronze.eodhd_fundamental_balance_sheet_observation
    GROUP BY ticker
),
source_by_security AS (
    SELECT t.security_id, COUNT(*) AS historical_tickers,
           SUM(COALESCE(r.requests, 0)) AS recorded_requests,
           BOOL_OR(COALESCE(r.http_success, FALSE)) AS http_success,
           SUM(COALESCE(o.source_records, 0)) AS source_records,
           SUM(COALESCE(o.filed_records, 0)) AS filed_records,
           SUM(COALESCE(o.usable_records, 0)) AS usable_records
    FROM security_tickers t
    LEFT JOIN request_by_ticker r USING (ticker)
    LEFT JOIN observation_by_ticker o USING (ticker)
    GROUP BY t.security_id
),
pit_by_security AS (
    SELECT s.security_id,
           COUNT(DISTINCT u.date) FILTER (WHERE p.shares_pit_available)
               AS pit_covered_rows,
           BOOL_OR(u.date = s.first_date AND COALESCE(p.shares_pit_available, FALSE))
               AS covers_research_start,
           MIN(p.shares_filing_date) FILTER (WHERE p.shares_pit_available)
               AS earliest_usable_filing_date
    FROM sample s
    JOIN silver.research_universe_eligibility u
      ON u.security_id = s.security_id AND u.primary_research_eligible_exchange
    LEFT JOIN silver.security_daily_shares_outstanding_pit p
      ON p.security_id = u.security_id AND p.date = u.date
    GROUP BY s.security_id
),
liquidity_by_security AS (
    SELECT s.security_id,
           MEDIAN(b.close * b.volume) FILTER (
               WHERE b.close > 0 AND b.volume > 0
           ) AS median_dollar_volume_proxy
    FROM sample s
    JOIN silver.research_universe_eligibility u
      ON u.security_id = s.security_id AND u.primary_research_eligible_exchange
    JOIN silver.security_daily_return_basis b
      ON b.security_id = u.security_id AND b.date = u.date
    GROUP BY s.security_id
)
SELECT s.*, x.historical_tickers, x.recorded_requests,
       x.http_success, x.source_records, x.filed_records, x.usable_records,
       p.pit_covered_rows, p.covers_research_start,
       p.earliest_usable_filing_date,
       l.median_dollar_volume_proxy
FROM sample s
LEFT JOIN source_by_security x USING (security_id)
LEFT JOIN pit_by_security p USING (security_id)
LEFT JOIN liquidity_by_security l USING (security_id)
ORDER BY s.history_decile, s.security_id
"""


def audit(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    frame = con.execute(AUDIT_SQL).df()
    if len(frame) != 200 or frame["security_id"].duplicated().any():
        raise RuntimeError(f"Expected 200 distinct securities, got {len(frame)}")
    for col in ("recorded_requests", "source_records", "filed_records",
                "usable_records", "pit_covered_rows"):
        frame[col] = frame[col].fillna(0).astype(int)
    frame["http_success"] = frame["http_success"].fillna(False).astype(bool)
    frame["covers_research_start"] = frame["covers_research_start"].fillna(False).astype(bool)
    frame["pit_row_coverage"] = frame["pit_covered_rows"] / frame["research_rows"]
    frame["filing_date_record_share"] = (
        frame["filed_records"] / frame["source_records"].replace(0, float("nan"))
    )
    frame["all_records_have_filing_date"] = (
        (frame["source_records"] > 0)
        & (frame["source_records"] == frame["filed_records"])
    )
    return frame


def summarize(frame: pd.DataFrame) -> dict:
    low_liquidity_cutoff = frame["median_dollar_volume_proxy"].quantile(0.25)
    flags = {
        "short_history_at_most_252_rows": frame["research_rows"] <= 252,
        "ended_before_2025": pd.to_datetime(frame["last_date"]) < pd.Timestamp("2025-01-01"),
        "research_start_before_2011": pd.to_datetime(frame["first_date"]) < pd.Timestamp("2011-01-01"),
        "lowest_quartile_dollar_volume_proxy": (
            frame["median_dollar_volume_proxy"] <= low_liquidity_cutoff
        ),
    }
    groups = {}
    for name, flag in flags.items():
        subset = frame.loc[flag.fillna(False)]
        groups[name] = {
            "securities": int(len(subset)),
            "no_usable_source": int((subset["usable_records"] == 0).sum()),
            "missing_pit_at_start": int((~subset["covers_research_start"]).sum()),
            "median_pit_row_coverage": float(subset["pit_row_coverage"].median())
                if len(subset) else None,
        }
    by_decile = frame.groupby("history_decile").agg(
        securities=("security_id", "size"),
        http_success=("http_success", "mean"),
        pit_at_start=("covers_research_start", "mean"),
        pit_row_coverage=("pit_row_coverage", "mean"),
    ).reset_index().to_dict(orient="records")
    return {
        "sample_securities": len(frame),
        "http_success_rate": float(frame["http_success"].mean()),
        "any_usable_source_rate": float((frame["usable_records"] > 0).mean()),
        "pit_at_research_start_rate": float(frame["covers_research_start"].mean()),
        "pit_row_coverage_weighted": float(
            frame["pit_covered_rows"].sum() / frame["research_rows"].sum()
        ),
        "all_records_filed_security_rate": float(frame["all_records_have_filing_date"].mean()),
        "filing_date_record_share": float(
            frame["filed_records"].sum() / frame["source_records"].sum()
        ) if frame["source_records"].sum() else None,
        "group_gaps": groups,
        "history_deciles": by_decile,
        "notes": [
            "HTTP success uses recorded Bronze responses; no API request is made.",
            "Research-start coverage uses actual Silver filing-date-based PIT availability.",
            "Dollar volume is a liquidity proxy, not a market-cap or size classification.",
            "A security may have multiple historical tickers; source records are counted per ticker.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with connect(read_only=True) as con:
        frame = audit(con)
    summary = summarize(frame)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_dir / "sample.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for key in ("http_success_rate", "any_usable_source_rate",
                "pit_at_research_start_rate", "pit_row_coverage_weighted",
                "all_records_filed_security_rate", "filing_date_record_share"):
        value = summary[key]
        print(f"{key}: {value:.2%}" if value is not None else f"{key}: n/a")
    print(f"Saved {args.output_dir / 'summary.json'} and sample.csv")


if __name__ == "__main__":
    main()
