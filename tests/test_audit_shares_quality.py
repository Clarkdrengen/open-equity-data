import duckdb

from open_equity_data.audit_shares_quality import audit, summarize


def test_deterministic_sample_uses_filing_date_pit_availability():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver; CREATE SCHEMA bronze")
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT i AS security_id, d AS date, 'T' || CAST(i AS VARCHAR) AS ticker,
               TRUE AS primary_research_eligible_exchange
        FROM range(1, 201) s(i),
             (VALUES (DATE '2023-01-02'), (DATE '2023-01-03')) days(d)
    """)
    con.execute("""
        CREATE TABLE bronze.eodhd_fundamental_balance_sheet_request AS
        SELECT 'T' || CAST(i AS VARCHAR) AS ticker, 200 AS http_status
        FROM range(1, 201) s(i)
    """)
    con.execute("""
        CREATE TABLE bronze.eodhd_fundamental_balance_sheet_observation AS
        SELECT 'T' || CAST(i AS VARCHAR) AS ticker, DATE '2022-12-31' AS period_date,
               CASE WHEN i <= 150 THEN DATE '2023-01-02' ELSE NULL END AS filing_date,
               1000.0 AS common_stock_shares_outstanding
        FROM range(1, 201) s(i)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT security_id, date, i <= 100 AS shares_pit_available,
               CASE WHEN i <= 100 THEN DATE '2023-01-02' ELSE NULL END
                   AS shares_filing_date
        FROM silver.research_universe_eligibility, LATERAL (SELECT security_id AS i)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_return_basis AS
        SELECT security_id, date, 10.0 AS close, 1000 AS volume
        FROM silver.research_universe_eligibility
    """)
    frame = audit(con)
    assert len(frame) == 200
    assert frame["history_decile"].value_counts().eq(20).all()
    assert frame["filing_date_record_share"].fillna(0).sum() == 150
    summary = summarize(frame)
    assert summary["http_success_rate"] == 1.0
    assert summary["any_usable_source_rate"] == 0.75
    assert summary["pit_at_research_start_rate"] == 0.5
    assert summary["pit_row_coverage_weighted"] == 0.5
    assert summary["all_records_filed_security_rate"] == 0.75
