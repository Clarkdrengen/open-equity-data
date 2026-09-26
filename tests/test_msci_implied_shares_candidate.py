import duckdb

from open_equity_data.build_msci_implied_shares_candidate import build


def test_implied_shares_require_unique_cap_and_security_and_prior_price():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.msci_usa_observation AS
        SELECT * FROM (VALUES
          ('source', 2, DATE '2018-09-30', 'US0378331005', 100.0, 'valid_isin'),
          ('source', 3, DATE '2018-09-30', 'US0378331005', 100.0, 'valid_isin'),
          ('source', 4, DATE '2018-09-30', 'US67066G1040', 200.0, 'valid_isin'),
          ('source', 5, DATE '2018-09-30', 'US67066G1040', 210.0, 'valid_isin'),
          ('source', 6, DATE '2018-09-30', 'US64110L1061', 300.0, 'valid_isin'),
          ('source', 7, DATE '2018-09-30', 'NA', NULL, 'na_padding')
        ) v(source_sha256, source_row_number, observation_date, isin,
            mktcap_as_supplied, parse_status)
    """)
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT * FROM (VALUES
          (1, 'AAPL', DATE '2018-09-28', 'US0378331005', TRUE),
          (1, 'AAPL', DATE '2018-09-27', 'US0378331005', TRUE),
          (2, 'NVDA', DATE '2018-09-28', 'US67066G1040', TRUE),
          (3, 'NFLX', DATE '2018-09-28', 'US64110L1061', TRUE),
          (4, 'NFLX2', DATE '2018-09-28', 'US64110L1061', TRUE),
          (5, 'AAPL_OLD', DATE '2018-10-01', 'US0378331005', TRUE)
        ) v(security_id, ticker, date, isin, primary_research_eligible_exchange)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv AS
        SELECT * FROM (VALUES
          (1, 'AAPL', DATE '2018-09-28', 50.0),
          (1, 'AAPL', DATE '2018-09-27', 40.0),
          (2, 'NVDA', DATE '2018-09-28', 20.0),
          (3, 'NFLX', DATE '2018-09-28', 30.0),
          (4, 'NFLX2', DATE '2018-09-28', 30.0),
          (5, 'AAPL_OLD', DATE '2018-10-01', 100.0)
        ) v(security_id, ticker, date, close)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT * FROM (VALUES
          (1, 'AAPL', DATE '2018-09-28', 2000.0,
           DATE '2018-08-01', 58, TRUE, FALSE),
          (2, 'NVDA', DATE '2018-09-28', 10000000.0,
           DATE '2018-08-01', 58, TRUE, FALSE)
        ) v(security_id, ticker, date, shares_outstanding,
            shares_filing_date, shares_age_days, shares_pit_available,
            ticker_identity_ambiguous)
    """)
    statuses = build(con)
    assert [(s, scale, n) for s, scale, n, *_ in statuses] == [
        ('ambiguous_security_id', 'not_comparable', 2),
        ('candidate_usd_millions_assumed', 'near_1000x_high', 1),
        ('conflicting_source_caps', 'not_comparable', 1),
    ]
    assert con.execute("""
        SELECT implied_shares_usd_millions_assumed, price_date, source_rows
        FROM silver.msci_implied_shares_candidate WHERE isin = 'US0378331005'
    """).fetchone() == (2_000_000.0, __import__('datetime').date(2018, 9, 28), 2)
    assert con.execute("""
        SELECT COUNT(*) FROM silver.msci_implied_shares_candidate
        WHERE candidate_status <> 'candidate_usd_millions_assumed'
          AND implied_shares_usd_millions_assumed IS NOT NULL
    """).fetchone()[0] == 0
    assert con.execute("""
        SELECT implied_to_eodhd_ratio, scale_diagnostic
        FROM silver.msci_implied_shares_scale_audit WHERE isin = 'US0378331005'
    """).fetchone() == (1000.0, 'near_1000x_high')
