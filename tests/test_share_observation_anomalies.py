import duckdb

from open_equity_data.audit_share_observation_anomalies import build, summary


def test_source_record_audit_groups_days_and_catches_persistent_bad_scale():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, ticker, date, ticker || '.US' AS eodhd_provider_symbol,
               period_date AS shares_period_date,
               filing_date AS shares_filing_date,
               raw_shares AS eodhd_filed_shares,
               raw_shares AS eodhd_normalized_shares,
               'no_later_recorded_split' AS eodhd_basis_status,
               source AS selected_source,
               CASE WHEN source = 'eodhd' THEN raw_shares * 25 END
                   AS market_cap_candidate,
               25.0 AS close, msci_shares AS msci_current_shares_candidate,
               NULL::DOUBLE AS manual_current_shares_candidate,
               1.0 AS current_split_multiplier,
               FALSE AS eodhd_observation_invalidated
        FROM (VALUES
            (1, 'A', DATE '2020-01-06', DATE '2019-12-31',
                DATE '2020-01-03', 40000000.0, 'eodhd', NULL::DOUBLE),
            (1, 'A', DATE '2020-01-07', DATE '2019-12-31',
                DATE '2020-01-03', 40000000.0, 'eodhd', NULL::DOUBLE),
            (1, 'A', DATE '2020-04-03', DATE '2020-03-31',
                DATE '2020-04-02', 40100000.0, 'eodhd', NULL::DOUBLE),
            (1, 'A', DATE '2020-07-03', DATE '2020-06-30',
                DATE '2020-07-02', 40200000.0, 'eodhd', NULL::DOUBLE),
            (1, 'A', DATE '2020-10-03', DATE '2020-09-30',
                DATE '2020-10-02', 40000000000.0, 'eodhd', NULL::DOUBLE),
            (2, 'B', DATE '2020-01-06', DATE '2019-12-31',
                DATE '2020-01-03', 40000000000.0, 'msci', 40000000.0),
            (2, 'B', DATE '2020-01-07', DATE '2019-12-31',
                DATE '2020-01-03', 40000000000.0, 'msci', 40000000.0)
        ) v(security_id, ticker, date, period_date, filing_date,
            raw_shares, source, msci_shares)
    """)
    build(con)
    rows = con.execute("""
        SELECT security_id, priced_days, review_reason, robust_z
        FROM silver.share_observation_anomaly_audit
        WHERE security_id = 2 OR eodhd_filed_shares = 40000000000
        ORDER BY security_id
    """).fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [
        (1, 1, 'adjacent_10x'), (2, 2, 'cross_source_10x')]
    assert rows[0][3] > 8
    assert sum(row[1] for row in summary(con)) == 5
