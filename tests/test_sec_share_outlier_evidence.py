from datetime import date

import duckdb

from open_equity_data.populate_sec_share_outlier_evidence import stage


def test_staged_replacements_are_dated_and_target_only_exact_vendor_record():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT * FROM (VALUES
          (7430, 'FRG', DATE '2021-03-09'),
          (7430, 'FRG', DATE '2021-08-03'),
          (7430, 'FRG', DATE '2021-08-04'),
          (7430, 'FRG', DATE '2021-11-02'),
          (7430, 'FRG', DATE '2021-11-03'),
          (7430, 'FRG', DATE '2021-11-04'),
          (7430, 'FRG', DATE '2022-02-25'),
          (7430, 'FRG', DATE '2022-03-01'),
          (9376, 'HYLN', DATE '2021-02-26')
        ) t(security_id, ticker, date)
    """)
    con.execute("""
        CREATE TABLE silver.security_shares_outstanding_effective AS
        SELECT * FROM (VALUES
          ('FRG', 'FRG.US', DATE '2020-11-04', DATE '2020-09-30',
           39692384000.0),
          ('FRG', 'FRG.US', DATE '2021-08-03', DATE '2021-06-30',
           40905567000.0),
          ('FRG', 'FRG.US', DATE '2021-11-02', DATE '2021-09-30',
           40973736000.0),
          ('FRG', 'FRG.US', DATE '2021-11-04', DATE '2021-10-01',
           40295469.0),
          ('FRG', 'FRG.US', DATE '2022-02-23', DATE '2021-12-31',
           41081519000.0),
          ('FRG', 'FRG.US', DATE '2022-03-01', DATE '2022-01-01',
           42000000.0),
          ('HYLN', 'HYLN.US', DATE '2021-02-26', DATE '2020-12-31',
           104324059000.0)
        ) t(ticker, provider_symbol, filing_date, period_date,
            shares_outstanding)
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT * FROM (VALUES
          (7430, 'FRG', 'Franchise Group, Inc.'),
          (9376, 'HYLN', 'Hyliion Holdings Corp.')
        ) t(security_id, ticker, bronze_security_name)
    """)
    result = stage(con)
    assert [(r[0], r[3], r[6]) for r in result] == [
        ('FRG', 2, 2), ('FRG', 2, 2), ('FRG', 4, 2), ('HYLN', 1, 1),
    ]
    assert con.execute("""
        SELECT ticker, price_date, sourced_shares, target_shares
        FROM sec_share_outlier_stage ORDER BY ticker, price_date
    """).fetchall() == [
        ('FRG', date(2021, 3, 9), 40087792.0,
         39692384000.0),
        ('FRG', date(2021, 8, 3), 40087792.0,
         40905567000.0),
        ('FRG', date(2021, 8, 4), 40228467.0,
         40905567000.0),
        ('FRG', date(2021, 11, 2), 40228467.0,
         40973736000.0),
        ('FRG', date(2021, 11, 3), 40295469.0,
         40973736000.0),
        ('FRG', date(2021, 11, 4), 40295469.0, None),
        ('FRG', date(2022, 2, 25), 40295469.0, 41081519000.0),
        ('FRG', date(2022, 3, 1), 40295469.0, None),
        ('HYLN', date(2021, 2, 26), 170255200.0,
         104324059000.0),
    ]
