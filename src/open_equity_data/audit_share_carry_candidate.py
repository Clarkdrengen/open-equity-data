"""Build the Silver PIT share carry candidate and print its universe impact."""

from pathlib import Path

from open_equity_data.db import connect


SQL_DIR = Path(__file__).resolve().parents[2] / "sql/silver"
BUILD_FILES = (
    "create_security_daily_share_carry_candidate.sql",
    "create_security_daily_market_cap_candidate.sql",
    "create_research_market_cap_weighted_candidate.sql",
)


def main() -> None:
    with connect() as con:
        for filename in BUILD_FILES:
            print(f"Building {filename}...", flush=True)
            con.execute((SQL_DIR / filename).read_text())
        print("status | issue-days | issues")
        for row in con.execute("""
            SELECT candidate_status, COUNT(*), COUNT(DISTINCT security_id)
            FROM silver.security_daily_share_carry_candidate
            GROUP BY 1 ORDER BY 2 DESC
        """).fetchall():
            print(*row, sep=" | ")
        print("daily cap-weighted coverage | minimum | median | maximum")
        row = con.execute("""
            SELECT MIN(weighted_issues_540::DOUBLE / eligible_issues),
                   MEDIAN(weighted_issues_540::DOUBLE / eligible_issues),
                   MAX(weighted_issues_540::DOUBLE / eligible_issues)
            FROM silver.research_market_cap_weighted_candidate
        """).fetchone()
        print("540 days", *row, sep=" | ")
        print("age window | available issue-days | newly available vs 365")
        for row in con.execute("""
            SELECT age_window, SUM(available)::BIGINT,
                   SUM(available AND NOT available_365)::BIGINT
            FROM silver.security_daily_share_carry_candidate,
                 LATERAL (VALUES ('365', available_365),
                                 ('540', available_540),
                                 ('730', available_730)) w(age_window, available)
            GROUP BY 1 ORDER BY 1
        """).fetchall():
            print(*row, sep=" | ")


if __name__ == "__main__":
    main()
