from datetime import date

import duckdb

from open_equity_data.build_msci_daily_share_preference import build


def test_msci_source_priority_waits_for_selected_session_and_keeps_previous_snapshot():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT 1 AS security_id, date::DATE AS date, 'AAA' AS ticker,
               TRUE AS primary_research_eligible_exchange
        FROM UNNEST([
            '2020-01-31', '2020-02-03', '2020-02-04', '2020-02-05',
            '2020-02-06', '2020-02-07', '2020-02-28', '2020-03-02',
            '2020-03-03', '2020-03-04', '2020-03-05', '2020-03-06'
        ]) AS t(date)
    """)
    con.execute("""
        CREATE TABLE silver.msci_m15d_rif_share_overlap_audit AS
        SELECT 1 AS security_id, 'AAA' AS ticker,
               observation_date::DATE AS observation_date,
               price_date::DATE AS price_date, '123' AS msci_security_code,
               'US0378331005' AS isin, closing_shares AS rif_closing_shares,
               1 AS closing_share_variants, 1 AS project_security_matches,
               'candidate_exact_code_name' AS identity_status
        FROM (VALUES
            ('2020-01-31', '2020-01-31', 1000.0),
            ('2020-02-28', '2020-02-28', 1200.0)
        ) v(observation_date, price_date, closing_shares)
    """)
    con.execute("""
        CREATE TABLE silver.msci_m15e_rif_share_overlap_audit AS
        SELECT * FROM silver.msci_m15d_rif_share_overlap_audit WHERE FALSE
    """)
    con.execute("""
        CREATE TABLE silver.security_shares_outstanding_effective AS
        SELECT 'AAA' AS ticker, DATE '2020-01-15' AS filing_date,
               DATE '2019-12-31' AS period_date,
               900.0 AS shares_outstanding
        UNION ALL SELECT 'BBB', DATE '2020-01-15', DATE '2019-12-31', 700.0
    """)
    con.execute("""
        CREATE TABLE silver.shares_ticker_identity_diagnostic AS
        SELECT 'AAA' AS ticker, FALSE AS ticker_identity_ambiguous
        UNION ALL SELECT 'BBB', FALSE
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT security_id, date, 1.0 AS cumulative_split_multiplier
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT security_id, date, ticker, 10.0 AS close,
               TRUE AS research_eligible
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        INSERT INTO silver.security_daily_ohlcv_reconciled VALUES
            (2, DATE '2020-01-14', 'BBB', 5.0, FALSE),
            (2, DATE '2020-02-03', 'BBB', 5.0, FALSE),
            (2, DATE '2021-01-14', 'BBB', 5.0, FALSE),
            (2, DATE '2021-01-15', 'BBB', 5.0, FALSE),
            (1, DATE '2021-02-26', 'AAA', 10.0, TRUE),
            (1, DATE '2021-03-01', 'AAA', 10.0, TRUE)
    """)
    con.execute("""
        INSERT INTO silver.security_daily_split_factor_reconciled VALUES
            (1, DATE '2021-02-26', 1.0),
            (1, DATE '2021-03-01', 1.0)
    """)
    rows = build(con)
    assert any(row[0:2] == (1, 'msci') for row in rows)
    lag1 = con.execute("""
        SELECT date, msci_snapshot_date, msci_current_shares_candidate,
               selected_source
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE security_id = 1
          AND date IN (DATE '2020-01-31', DATE '2020-02-03', DATE '2020-03-02')
        ORDER BY date
    """).fetchall()
    assert lag1[0][1:] == (None, None, 'eodhd')
    assert lag1[1][2:] == (1000.0, 'msci')
    assert lag1[2][2:] == (1200.0, 'msci')
    assert con.execute("""
        SELECT market_cap_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2020-03-02'
    """).fetchone()[0] == 12_000.0
    lag5 = con.execute("""
        SELECT date, msci_snapshot_date, msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag5_candidate
        WHERE security_id = 1 AND date IN (DATE '2020-02-06', DATE '2020-02-07',
                       DATE '2020-03-02', DATE '2020-03-06')
        ORDER BY date
    """).fetchall()
    assert [r[2] for r in lag5] == [None, 1000.0, 1000.0, 1200.0]
    assert con.execute("""
        SELECT COUNT(*) FROM silver.msci_daily_share_preference_lag22_candidate
        WHERE date <= DATE '2020-03-06'
          AND msci_current_shares_candidate IS NOT NULL
    """).fetchone()[0] == 0

    # Base rows are all dated prices, including a security absent from MSCI
    # and a price row outside the research eligibility table.
    assert con.execute("""
        SELECT selected_source, market_cap_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE security_id = 2 AND date = DATE '2020-02-03'
    """).fetchone() == ('eodhd', 3500.0)
    assert con.execute("""
        SELECT date, selected_source FROM
            silver.msci_daily_share_preference_lag1_candidate
        WHERE security_id = 2
        ORDER BY date
    """).fetchall() == [
        (date(2020, 1, 14), 'no_eligible_share_source'),
        (date(2020, 2, 3), 'eodhd'),
        (date(2021, 1, 14), 'eodhd'),
        (date(2021, 1, 15), 'no_eligible_share_source'),
    ]
    assert con.execute("""
        SELECT selected_source, msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2021-02-26'
    """).fetchone() == ('msci', 1200.0)
    assert con.execute("""
        SELECT selected_source, market_cap_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2021-03-01'
    """).fetchone() == ('no_eligible_share_source', None)

    con.execute("""
        UPDATE silver.security_shares_outstanding_effective
        SET shares_outstanding = 0 WHERE ticker = 'AAA'
    """)
    con.execute("""
        UPDATE silver.security_daily_split_factor_reconciled
        SET cumulative_split_multiplier = 2.0 WHERE date = DATE '2020-03-06'
    """)
    build(con)
    assert con.execute("""
        SELECT selected_source, msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2020-03-02'
    """).fetchone() == ('msci', 1200.0)
    assert con.execute("""
        SELECT msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag5_candidate
        WHERE date = DATE '2020-03-06'
    """).fetchone()[0] == 2400.0
