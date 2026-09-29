"""Build conservative SEC class-share overlay and daily market caps.

Requires the existing Bronze EODHD and SEC candidate loads and the Silver
identity, return, universe, and EODHD PIT tables. Rebuilds only the new tables.
"""

from __future__ import annotations

from pathlib import Path

from open_equity_data.db import connect


SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "silver"
FILES = (
    "create_security_daily_shares_resolved.sql",
    "create_security_daily_market_cap.sql",
)


def run(con, sql_dir: Path = SQL_DIR) -> dict:
    con.execute("BEGIN TRANSACTION")
    try:
        for filename in FILES:
            con.execute((sql_dir / filename).read_text())
        duplicates = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT security_id, date
                FROM silver.security_daily_shares_resolved
                GROUP BY 1, 2 HAVING COUNT(*) <> 1
            )
        """).fetchone()[0]
        cap_duplicates = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT security_id, date
                FROM silver.security_daily_market_cap
                GROUP BY 1, 2 HAVING COUNT(*) <> 1
            )
        """).fetchone()[0]
        violations = con.execute("""
            SELECT COUNT(*)
            FROM silver.security_daily_shares_resolved
            WHERE (simultaneous_class_candidate
                   AND shares_source = 'eodhd_issuer_total')
               OR (shares_filing_date > date AND shares_outstanding IS NOT NULL)
        """).fetchone()[0]
        summary = dict(con.execute("""
            SELECT shares_source, COUNT(*)
            FROM silver.security_daily_shares_resolved
            GROUP BY 1 ORDER BY 1
        """).fetchall())
        if duplicates or cap_duplicates or violations:
            raise RuntimeError(
                f"Invalid shares resolution: {duplicates} duplicate share dates, "
                f"{cap_duplicates} duplicate market-cap dates, "
                f"{violations} issuer-total/lookahead violations"
            )
        if summary.get("sec_class_filing", 0) == 0:
            raise RuntimeError(
                "No approved same-filing SEC class observations matched "
                "simultaneously eligible issues; inspect candidates first"
            )
        cap_rows, total_rows, class_rows, class_cap_rows = con.execute("""
            SELECT COUNT(market_cap), COUNT(*),
                   COUNT(*) FILTER (WHERE simultaneous_class_candidate),
                   COUNT(market_cap) FILTER (WHERE simultaneous_class_candidate)
            FROM silver.security_daily_market_cap
            JOIN silver.security_daily_shares_resolved USING (security_id, date)
        """).fetchone()
        market_days, matched_days = con.execute("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (
                       WHERE cap_weighted_security_count = eligible_security_count
                   )
            FROM silver.research_market_daily_weighted
        """).fetchone()
        con.execute("COMMIT")
        return {
            "share_source_rows": summary,
            "market_cap_rows": cap_rows,
            "eligible_rows": total_rows,
            "simultaneous_class_rows": class_rows,
            "simultaneous_class_market_cap_rows": class_cap_rows,
            "market_days": market_days,
            "full_cap_coverage_days": matched_days,
        }
    except BaseException:
        con.execute("ROLLBACK")
        raise


def main() -> None:
    with connect() as con:
        summary = run(con)
    for source, count in summary["share_source_rows"].items():
        print(f"{source}: {count:,}")
    print(
        f"Market caps: {summary['market_cap_rows']:,}/"
        f"{summary['eligible_rows']:,} eligible rows"
    )
    print(
        f"Simultaneous-class market caps: "
        f"{summary['simultaneous_class_market_cap_rows']:,}/"
        f"{summary['simultaneous_class_rows']:,} rows"
    )
    print(
        f"Full-cap-coverage market days: "
        f"{summary['full_cap_coverage_days']:,}/"
        f"{summary['market_days']:,} days"
    )


if __name__ == "__main__":
    main()
