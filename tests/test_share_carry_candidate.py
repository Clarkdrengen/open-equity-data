from pathlib import Path

import duckdb


SQL = (Path(__file__).resolve().parents[1] / "sql/silver"
       / "create_security_daily_share_carry_candidate.sql")


def test_carry_is_filed_date_causal_split_adjusted_and_excludes_multi_issue():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT * FROM (VALUES
          (1, DATE '2021-07-01', 'AAA', DATE '2020-01-01', DATE '2020-01-02', 100.0, FALSE),
          (1, DATE '2021-04-01', 'AAA', DATE '2020-01-01', DATE '2020-01-02', 100.0, FALSE),
          (1, DATE '2022-02-01', 'AAA', DATE '2020-01-01', DATE '2020-01-02', 100.0, FALSE),
          (2, DATE '2021-07-01', 'BBB', DATE '2020-01-01', DATE '2020-01-02', 200.0, FALSE),
          (3, DATE '2021-07-01', 'CCC', NULL::DATE, NULL::DATE, NULL::DOUBLE, FALSE)
        ) v(security_id, date, ticker, shares_period_date, shares_filing_date,
            shares_outstanding, ticker_identity_ambiguous)
    """)
    con.execute("""
        ALTER TABLE silver.security_daily_shares_outstanding_pit
        ADD COLUMN provider_symbol VARCHAR DEFAULT 'source'
    """)
    con.execute("""
        ALTER TABLE silver.security_daily_shares_outstanding_pit
        ADD COLUMN shares_source VARCHAR DEFAULT 'eodhd_balance_sheet'
    """)
    con.execute("""
        ALTER TABLE silver.security_daily_shares_outstanding_pit
        ADD COLUMN shares_age_days BIGINT
    """)
    con.execute("""
        UPDATE silver.security_daily_shares_outstanding_pit
        SET shares_age_days = date_diff('day', shares_filing_date, date)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT * FROM (VALUES
          (1, DATE '2020-01-01', 1.0),
          (1, DATE '2021-07-01', 2.0),
          (1, DATE '2021-04-01', 1.0),
          (1, DATE '2022-02-01', 2.0),
          (2, DATE '2021-07-01', 1.0),
          (3, DATE '2021-07-01', 1.0)
        ) v(security_id, date, cumulative_split_multiplier)
    """)
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate AS
        SELECT 2 AS security_id_a, 99 AS security_id_b
    """)
    con.execute(SQL.read_text())
    rows = con.execute("""
        SELECT security_id, date, candidate_status, estimated_current_shares,
               available_365, available_540, available_730
        FROM silver.security_daily_share_carry_candidate
        ORDER BY security_id, date
    """).fetchall()
    assert rows[0][2:] == ('candidate_usable', 100.0, False, True, True)
    assert rows[1][2:] == ('candidate_usable', 200.0, False, False, True)
    assert rows[2][2] == 'older_than_730_days'
    assert rows[2][3] is None
    assert rows[3][2] == 'multi_issue_issuer_total'
    assert rows[4][2] == 'no_prior_filed_shares'
