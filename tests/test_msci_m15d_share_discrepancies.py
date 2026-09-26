import duckdb

from open_equity_data.audit_msci_m15d_share_discrepancies import build


def test_1000x_is_flagged_only_without_identity_or_split_blockers():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute('''
        CREATE TABLE silver.msci_m15d_price_overlap_candidate AS
        SELECT * FROM (VALUES
          (1, 'AAA', DATE '2018-09-30', DATE '2018-09-28',
           'candidate_exact_code_name', 1, 1000000.0, 1200000.0),
          (2, 'BBB', DATE '2018-09-30', DATE '2018-09-28',
           'name_review', 1, 1000000.0, 1200000.0),
          (3, 'CCC', DATE '2018-09-30', DATE '2018-09-28',
           'candidate_exact_code_name', 1, 1000000.0, 1200000.0)
        ) v(security_id, ticker, observation_date, price_date,
            identity_status, project_security_matches, shares_today, closing_shares)
    ''')
    con.execute('''
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT * FROM (VALUES
          (1, 'AAA', DATE '2018-09-28', 1000.0, DATE '2018-08-01', DATE '2018-08-03', 56, TRUE, FALSE),
          (2, 'BBB', DATE '2018-09-28', 1000.0, DATE '2018-08-01', DATE '2018-08-03', 56, TRUE, FALSE),
          (3, 'CCC', DATE '2018-09-28', 1000.0, DATE '2018-08-01', DATE '2018-08-03', 56, TRUE, FALSE)
        ) v(security_id, ticker, date, shares_outstanding,
            shares_period_date, shares_filing_date, shares_age_days,
            shares_pit_available, ticker_identity_ambiguous)
    ''')
    con.execute('''
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT 3 AS security_id, DATE '2018-09-01' AS date,
               2.0 AS daily_split_ratio
    ''')
    build(con)
    assert con.execute('''
        SELECT security_id, comparable, intervening_split, today_scale_band,
               closing_scale_band
        FROM silver.msci_m15d_share_discrepancy_audit ORDER BY security_id
    ''').fetchall() == [
        (1, True, False, 'near_1000x_high', 'near_1000x_high'),
        (2, False, False, 'not_comparable', 'not_comparable'),
        (3, False, True, 'not_comparable', 'not_comparable'),
    ]
