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
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT security_id, date, ticker, 900.0 AS shares_outstanding,
               DATE '2020-01-15' AS shares_filing_date,
               DATE '2019-12-31' AS shares_period_date, 19 AS shares_age_days,
               TRUE AS shares_pit_available,
               FALSE AS ticker_identity_ambiguous
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT security_id, date, 1.0 AS cumulative_split_multiplier
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT security_id, date, 10.0 AS close, TRUE AS research_eligible
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate AS
        SELECT 1 AS security_id_a, 2 AS security_id_b WHERE FALSE
    """)
    rows = build(con)
    assert any(row[0:2] == (1, 'msci_preferred_where_both') for row in rows)
    lag1 = con.execute("""
        SELECT date, msci_snapshot_date, msci_current_shares_candidate,
               source_status
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date IN (DATE '2020-01-31', DATE '2020-02-03', DATE '2020-03-02')
        ORDER BY date
    """).fetchall()
    assert lag1[0][1:] == (None, None, 'eodhd_only_or_msci_not_yet_available')
    assert lag1[1][2:] == (1000.0, 'msci_preferred_where_both')
    assert lag1[2][2:] == (1200.0, 'msci_preferred_where_both')
    assert con.execute("""
        SELECT msci_market_cap_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2020-03-02'
    """).fetchone()[0] == 12_000.0
    lag5 = con.execute("""
        SELECT date, msci_snapshot_date, msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag5_candidate
        WHERE date IN (DATE '2020-02-06', DATE '2020-02-07',
                       DATE '2020-03-02', DATE '2020-03-06')
        ORDER BY date
    """).fetchall()
    assert [r[2] for r in lag5] == [None, 1000.0, 1000.0, 1200.0]
    assert con.execute("""
        SELECT COUNT(*) FROM silver.msci_daily_share_preference_lag22_candidate
        WHERE msci_current_shares_candidate IS NOT NULL
    """).fetchone()[0] == 0

    con.execute("""
        UPDATE silver.security_daily_shares_outstanding_pit
        SET shares_pit_available = FALSE WHERE date = DATE '2020-03-02'
    """)
    con.execute("""
        UPDATE silver.security_daily_split_factor_reconciled
        SET cumulative_split_multiplier = 2.0 WHERE date = DATE '2020-03-06'
    """)
    build(con)
    assert con.execute("""
        SELECT source_status, msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag1_candidate
        WHERE date = DATE '2020-03-02'
    """).fetchone() == ('msci_only_pending_policy', None)
    assert con.execute("""
        SELECT msci_current_shares_candidate
        FROM silver.msci_daily_share_preference_lag5_candidate
        WHERE date = DATE '2020-03-06'
    """).fetchone()[0] == 2400.0
