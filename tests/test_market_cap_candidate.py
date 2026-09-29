from pathlib import Path

import duckdb
import pytest


SQL_DIR = Path(__file__).resolve().parents[1] / "sql/silver"


def test_previous_close_cap_weights_and_covered_equal_weight():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.security_daily_share_carry_candidate AS
        SELECT * FROM (VALUES
          (1, DATE '2024-01-02', 'AAA', DATE '2022-10-01',
           DATE '2023-01-01', 366, 'eodhd', 'candidate_usable',
           100.0, FALSE, TRUE, TRUE),
          (2, DATE '2024-01-02', 'BBB', DATE '2023-10-01',
           DATE '2023-11-01', 62, 'eodhd', 'candidate_usable',
           10.0, TRUE, TRUE, TRUE),
          (3, DATE '2024-01-02', 'CCC', NULL::DATE,
           NULL::DATE, NULL::BIGINT, 'eodhd', 'no_prior_filed_shares',
           NULL::DOUBLE, FALSE, FALSE, FALSE)
        ) v(security_id, date, ticker, shares_period_date, shares_filing_date,
            shares_age_days, shares_source, candidate_status,
            estimated_current_shares, available_365, available_540, available_730)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT * FROM (VALUES
          (1, DATE '2024-01-02', 10.0, 'eodhd', TRUE),
          (2, DATE '2024-01-02', 10.0, 'eodhd', TRUE),
          (3, DATE '2024-01-02', 10.0, 'eodhd', TRUE)
        ) v(security_id, date, close, source, research_eligible)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_return_research AS
        SELECT * FROM (VALUES
          (1, DATE '2024-01-03', DATE '2024-01-02', 0.1, TRUE),
          (2, DATE '2024-01-03', DATE '2024-01-02', -0.1, TRUE),
          (3, DATE '2024-01-03', DATE '2024-01-02', 0.4, TRUE)
        ) v(security_id, date, previous_date, gross_total_return,
            final_research_eligible)
    """)
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT security_id, date, TRUE AS primary_research_eligible_exchange
        FROM silver.security_daily_return_research
    """)
    for name in ("create_security_daily_market_cap_candidate.sql",
                 "create_research_market_cap_weighted_candidate.sql"):
        con.execute((SQL_DIR / name).read_text())
    row = con.execute("""
        SELECT eligible_issues, weighted_issues_365, weighted_issues_540,
               equal_weight_full_return, equal_weight_covered_540,
               cap_weighted_return_365, cap_weighted_return_540
        FROM silver.research_market_cap_weighted_candidate
    """).fetchone()
    assert row[:3] == (3, 1, 2)
    assert row[3] == pytest.approx((0.1 - 0.1 + 0.4) / 3)
    assert row[4] == pytest.approx(0.0)
    assert row[5] == pytest.approx(-0.1)
    assert row[6] == pytest.approx((1000 * 0.1 + 100 * -0.1) / 1100)
