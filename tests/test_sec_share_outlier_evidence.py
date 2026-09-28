from datetime import date

import duckdb

from open_equity_data.populate_sec_share_outlier_evidence import stage
import open_equity_data.populate_sec_share_outlier_evidence as module


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
          (7430, 'FRG', DATE '2022-11-04'),
          (7430, 'FRG', DATE '2023-02-02'),
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
          ('FRG', 'FRG.US', DATE '2022-11-03', DATE '2022-09-30',
           39941287000.0),
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
        ('FRG', 2, 2), ('FRG', 2, 2), ('FRG', 4, 2),
        ('FRG', 2, 1), ('HYLN', 1, 1),
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
        ('FRG', date(2022, 11, 4), 38205831.0, 39941287000.0),
        ('FRG', date(2023, 2, 2), 38205831.0, 39941287000.0),
        ('HYLN', date(2021, 2, 26), 170255200.0,
         104324059000.0),
    ]


def test_frg_2022_application_preserves_other_bronze_rows(monkeypatch):
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute(module.MANUAL_SCHEMA.read_text())
    con.execute("""
        INSERT INTO bronze.eodhd_share_manual_adjustment (
            security_id, ticker, sourced_shares, shares_as_of_date,
            source_publication_date, source_name, source_url,
            source_document_id, source_excerpt, recorded_at, price_date)
        VALUES (9376, 'HYLN', 170255200, DATE '2021-02-23',
                DATE '2021-02-26', 'SEC', 'https://sec.gov/hyln',
                'older-hyln', '170,255,200', current_timestamp,
                DATE '2021-02-26')
    """)
    con.execute("""
        CREATE TEMP TABLE sec_share_outlier_stage AS
        SELECT security_id, ticker, price_date,
               ticker || '.US' AS target_provider_symbol,
               DATE '2022-09-30' AS target_period_date,
               DATE '2022-11-03' AS target_filing_date,
               39941287000.0 AS target_shares,
               38205831.0 AS sourced_shares,
               DATE '2022-10-31' AS shares_as_of_date,
               DATE '2022-11-03' AS source_publication_date,
               'SEC 10-Q' AS source_name,
               'https://www.sec.gov/example' AS source_url,
               '0001528930-22-000046' AS source_document_id,
               '38,205,831 common shares' AS source_excerpt
        FROM (VALUES
            (7430, 'FRG', DATE '2022-11-04'),
            (7430, 'FRG', DATE '2023-02-02')
        ) v(security_id, ticker, price_date)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, price_date AS date, 'eodhd' AS selected_source,
               39941287000.0 AS selected_shares_candidate,
               32.66 * 39941287000.0 AS market_cap_candidate
        FROM sec_share_outlier_stage
    """)

    def rebuild(conn, *, manage_transaction):
        assert not manage_transaction
        conn.execute("""
            UPDATE silver.security_daily_market_cap_source_priority_candidate c
               SET selected_source = 'manual_sourced',
                   selected_shares_candidate = 38205831.0,
                   market_cap_candidate = 32.66 * 38205831.0
            WHERE EXISTS (
                SELECT 1 FROM bronze.eodhd_share_manual_adjustment a
                WHERE a.security_id = c.security_id AND a.price_date = c.date
                  AND a.source_document_id = '0001528930-22-000046'
            )
        """)
    monkeypatch.setattr(module, 'build', rebuild)
    assert module.apply_frg_2022(con)[:3] == (
        2, date(2022, 11, 4), date(2023, 2, 2))
    assert module.apply_frg_2022(con)[0] == 2
    assert con.execute("""
        SELECT ticker, source_document_id, COUNT(*)
        FROM bronze.eodhd_share_manual_adjustment
        GROUP BY ALL ORDER BY ticker
    """).fetchall() == [
        ('FRG', '0001528930-22-000046', 2),
        ('HYLN', 'older-hyln', 1),
    ]
