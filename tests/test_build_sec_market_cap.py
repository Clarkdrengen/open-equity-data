import duckdb
import pytest

from open_equity_data.build_sec_market_cap import run


def fixture_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate AS
        SELECT * FROM (VALUES
            ('0001', 1, 'A', 2, 'B', DATE '2023-01-02', DATE '2023-01-03'),
            ('0002', 3, 'C', 4, 'D', DATE '2023-01-02', DATE '2023-01-03')
        ) AS v(cik, security_id_a, ticker_a, security_id_b, ticker_b,
               overlap_start, overlap_end)
    """)
    con.execute("""
        CREATE TABLE silver.sec_class_share_candidate AS
        SELECT * FROM (VALUES
            ('0001', 'A', DATE '2023-01-02', DATE '2022-12-31', 'file1',
             'classA', 100.0, 'sha1', 'mapped_unique_symbol'),
            ('0001', 'B', DATE '2023-01-02', DATE '2022-12-31', 'file1',
             'classB', 200.0, 'sha1', 'mapped_unique_symbol')
        ) AS v(cik, trading_symbol, filing_date, shares_as_of_date,
               accession_number, class_member, shares_outstanding,
               source_document_sha256, symbol_mapping_status)
    """)
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT i AS security_id,
               CASE i WHEN 1 THEN 'A' WHEN 2 THEN 'B' WHEN 3 THEN 'C'
                      WHEN 4 THEN 'D' ELSE 'E' END AS ticker,
               d AS date, TRUE AS primary_research_eligible_exchange
        FROM range(1, 6) v(i),
             (VALUES (DATE '2023-01-02'), (DATE '2023-01-03')) days(d)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT security_id, date, 1000.0 AS shares_outstanding,
               TRUE AS shares_pit_available,
               DATE '2023-01-02' AS shares_filing_date
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT security_id, date, 'source' AS source,
               CASE security_id WHEN 1 THEN 10.0 WHEN 2 THEN 20.0
                    WHEN 3 THEN 30.0 WHEN 4 THEN 40.0 ELSE 5.0 END AS close
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_return_research AS
        SELECT security_id, date, DATE '2023-01-02' AS previous_date,
               CASE security_id WHEN 1 THEN 0.1 WHEN 2 THEN -0.1
                    WHEN 3 THEN 0.03 WHEN 4 THEN -0.02 ELSE 0.2 END
                    AS gross_total_return,
               TRUE AS final_research_eligible
        FROM silver.research_universe_eligibility
        WHERE date = DATE '2023-01-03'
    """)
    return con


def test_sec_overrides_only_dated_supported_classes_and_lag_weights():
    con = fixture_db()
    summary = run(con)
    assert summary["share_source_rows"] == {
        "eodhd_issuer_total": 2, "missing_sec_class": 4,
        "sec_class_filing": 4,
    }
    rows = con.execute("""
        SELECT security_id, shares_outstanding, market_cap
        FROM silver.security_daily_market_cap
        WHERE date = DATE '2023-01-02'
        ORDER BY security_id
    """).fetchall()
    assert rows == [(1, 100, 1000), (2, 200, 4000), (3, None, None),
                    (4, None, None), (5, 1000, 5000)]
    weighted = con.execute("""
        SELECT cap_weighted_security_count, equal_weight_return_matched,
               cap_weight_return_matched
        FROM silver.research_market_daily_weighted
    """).fetchone()
    assert weighted[0] == 3
    assert weighted[1] == pytest.approx((0.1 - 0.1 + 0.2) / 3)
    assert weighted[2] == pytest.approx((100 - 400 + 1000) / 10000)


def test_no_sec_pair_rolls_back_all_new_tables():
    con = fixture_db()
    con.execute("DELETE FROM silver.sec_class_share_candidate")
    with pytest.raises(RuntimeError, match="No approved"):
        run(con)
    assert con.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'silver'
          AND table_name = 'security_daily_market_cap'
    """).fetchone()[0] == 0


def test_sec_filing_is_not_applied_before_its_date():
    con = fixture_db()
    con.execute("""
        INSERT INTO silver.sec_class_share_candidate VALUES
            ('0002', 'C', DATE '2023-01-03', DATE '2022-12-31',
             'file2', 'classC', 300.0, 'sha2', 'mapped_unique_symbol'),
            ('0002', 'D', DATE '2023-01-03', DATE '2022-12-31',
             'file2', 'classD', 400.0, 'sha2', 'mapped_unique_symbol')
    """)
    run(con)
    rows = con.execute("""
        SELECT date, shares_source, shares_outstanding,
               sec_accession_number, sec_document_sha256
        FROM silver.security_daily_shares_resolved
        WHERE security_id = 3 ORDER BY date
    """).fetchall()
    assert rows[0][1:] == ("missing_sec_class", None, None, None)
    assert rows[1][1:] == ("sec_class_filing", 300, "file2", "sha2")
    weighted_count = con.execute("""
        SELECT cap_weighted_security_count
        FROM silver.research_market_daily_weighted
    """).fetchone()[0]
    assert weighted_count == 3  # no lookahead from the date-3 filing
