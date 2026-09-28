from datetime import date

import duckdb

from open_equity_data.build_msci_daily_share_preference import (
    build,
    top_eodhd_outliers,
)


def test_month_end_msci_priority_and_365_day_carry_without_future_selection():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT 1 AS security_id, date::DATE AS date, 'AAA' AS ticker,
               TRUE AS primary_research_eligible_exchange
        FROM UNNEST([
            '2020-01-30', '2020-01-31', '2020-02-03', '2020-02-04', '2020-02-05',
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
        SELECT 'AAA' AS ticker, 'AAA.US' AS provider_symbol,
               DATE '2020-01-15' AS filing_date,
               DATE '2019-12-31' AS period_date,
               900.0 AS shares_outstanding,
               'eodhd_balance_sheet' AS shares_source
        UNION ALL SELECT 'BBB', 'BBB.US', DATE '2020-01-15', DATE '2019-12-31',
                         700.0, 'eodhd_balance_sheet'
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
        SELECT security_id, date, ticker, 10.0 AS close, 'dolt' AS source,
               TRUE AS research_eligible
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        INSERT INTO silver.security_daily_ohlcv_reconciled VALUES
            (2, DATE '2020-01-14', 'BBB', 5.0, 'dolt', FALSE),
            (2, DATE '2020-02-03', 'BBB', 5.0, 'dolt', FALSE),
            (2, DATE '2021-01-14', 'BBB', 5.0, 'dolt', FALSE),
            (2, DATE '2021-01-15', 'BBB', 5.0, 'dolt', FALSE),
            (1, DATE '2021-02-26', 'AAA', 10.0, 'eodhd', TRUE),
            (1, DATE '2021-03-01', 'AAA', 10.0, 'eodhd', TRUE)
    """)
    con.execute("""
        INSERT INTO silver.security_daily_split_factor_reconciled VALUES
            (1, DATE '2021-02-26', 1.0),
            (1, DATE '2021-03-01', 1.0)
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT 1 AS security_id, 'AAA' AS ticker,
               'Alpha' AS bronze_security_name,
               'Common Stock' AS resolved_instrument_type,
               'NYSE' AS resolved_exchange
        UNION ALL SELECT 2, 'BBB', 'Beta', 'Common Stock', 'NASDAQ'
    """)
    rows = build(con)
    assert any(row[0] == 'msci' for row in rows)
    peaks = top_eodhd_outliers(con, 2)
    assert [r[2] for r in peaks] == ['AAA', 'BBB']
    assert peaks[1][6:9] == (3500.0, 5.0, 700.0)
    selected = con.execute("""
        SELECT date, msci_snapshot_date, msci_current_shares_candidate,
               selected_source
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1
          AND date IN (DATE '2020-01-30', DATE '2020-01-31',
                       DATE '2020-02-03', DATE '2020-02-28',
                       DATE '2020-03-02')
        ORDER BY date
    """).fetchall()
    assert selected[0][1:] == (None, None, 'eodhd')
    assert selected[1][2:] == (1000.0, 'msci')
    assert selected[2][2:] == (1000.0, 'msci')
    assert selected[3][2:] == (1200.0, 'msci')
    assert selected[4][2:] == (1200.0, 'msci')
    assert con.execute("""
        SELECT market_cap_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE date = DATE '2020-03-02'
    """).fetchone()[0] == 12_000.0

    # Base rows are all dated prices, including a security absent from MSCI
    # and a price row outside the research eligibility table.
    assert con.execute("""
        SELECT selected_source, market_cap_candidate,
               price_source, eodhd_share_source
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 2 AND date = DATE '2020-02-03'
    """).fetchone() == ('eodhd', 3500.0, 'dolt', 'eodhd_balance_sheet')
    assert con.execute("""
        SELECT date, selected_source FROM
            silver.security_daily_market_cap_source_priority_candidate
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
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE date = DATE '2021-02-26'
    """).fetchone() == ('msci', 1200.0)

    # A manual source can invalidate an exact EODHD observation, then fill
    # the gap only after publication. MSCI and other EODHD data keep priority.
    con.execute("""
        INSERT INTO bronze.eodhd_share_manual_adjustment VALUES
        (2, 'BBB', 'BBB.US', DATE '2019-12-31', DATE '2020-01-15',
         700.0, 720.0, DATE '2020-01-31', DATE '2020-02-01',
         'filing', 'https://example.org/filing', 'filing-1',
         '720 shares as of January 31', NULL, TIMESTAMP '2020-02-02',
         DATE '2020-02-03')
    """)
    con.execute("""
        INSERT INTO bronze.eodhd_share_manual_adjustment VALUES
        (1, 'AAA', 'AAA.US', DATE '2019-12-31', DATE '2020-01-15',
         900.0, 920.0, DATE '2020-01-31', DATE '2020-02-01',
         'filing', 'https://example.org/other', 'filing-2',
         '920 shares as of January 31', NULL, TIMESTAMP '2020-02-02',
         DATE '2020-02-03')
    """)
    con.execute("""
        INSERT INTO bronze.eodhd_share_manual_adjustment VALUES
        (3, 'CCC', NULL, NULL, NULL, NULL, 50.0,
         DATE '2020-02-28', DATE '2020-03-01', 'filing',
         'https://example.org/third', 'filing-3',
         '50 shares as of February 28', NULL, TIMESTAMP '2020-03-01',
         DATE '2020-03-02')
    """)
    con.execute("""
        INSERT INTO silver.security_daily_ohlcv_reconciled VALUES
        (3, DATE '2020-03-02', 'CCC', 2.0, 'dolt', FALSE)
    """)
    build(con)
    assert con.execute("""
        SELECT selected_source, selected_shares_candidate,
               eodhd_filed_shares, manual_document_id,
               market_cap_candidate, eodhd_observation_invalidated,
               msci_current_shares_candidate,
               manual_current_shares_candidate,
               eodhd_current_shares_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 2 AND date = DATE '2020-02-03'
    """).fetchone() == ('manual_sourced', 720.0, 700.0, 'filing-1',
                        3600.0, True, None, 720.0, None)
    assert con.execute("""
        SELECT selected_source, selected_shares_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1 AND date = DATE '2020-02-03'
    """).fetchone() == ('msci', 1000.0)
    assert con.execute("""
        SELECT selected_source, selected_shares_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1 AND date = DATE '2020-01-30'
    """).fetchone() == ('no_eligible_share_source', None)
    assert con.execute("""
        SELECT shares_outstanding FROM silver.security_shares_outstanding_effective
        WHERE ticker = 'BBB'
    """).fetchone()[0] == 700.0
    assert con.execute("""
        SELECT selected_source, selected_shares_candidate,
               market_cap_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 3 AND date = DATE '2020-03-02'
    """).fetchone() == ('manual_sourced', 50.0, 100.0)
    assert con.execute("""
        SELECT selected_source, market_cap_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1 AND date = DATE '2021-03-01'
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
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1 AND date = DATE '2020-03-02'
    """).fetchone() == ('msci', 1200.0)
    assert con.execute("""
        SELECT msci_current_shares_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE security_id = 1 AND date = DATE '2020-03-06'
    """).fetchone()[0] == 2400.0
