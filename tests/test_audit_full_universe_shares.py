import duckdb

from open_equity_data.audit_full_universe_shares import audit


def test_gap_reasons_distinguish_absent_source_start_and_age():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver; CREATE SCHEMA bronze")
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit (
          security_id BIGINT, ticker VARCHAR, date DATE,
          shares_pit_available BOOLEAN, shares_outstanding DOUBLE,
          ticker_identity_ambiguous BOOLEAN, shares_age_days INTEGER
        );
        CREATE TABLE silver.security_shares_outstanding_effective (
          ticker VARCHAR, filing_date DATE
        );
        CREATE TABLE bronze.eodhd_fundamental_balance_sheet_request (
          ticker VARCHAR, http_status INTEGER, usable_record_count INTEGER
        );
    """)
    con.execute("""
        INSERT INTO silver.security_daily_shares_outstanding_pit VALUES
          (1, 'AAA', DATE '2020-01-01', FALSE, NULL, FALSE, NULL),
          (1, 'AAA', DATE '2020-02-02', TRUE, 100, FALSE, 1),
          (2, 'BBB', DATE '2020-01-01', FALSE, NULL, FALSE, NULL),
          (3, 'CCC', DATE '2020-01-01', FALSE, 200, FALSE, 400),
          (4, 'DDD', DATE '2020-01-01', FALSE, 300, TRUE, 400);
        INSERT INTO silver.security_shares_outstanding_effective VALUES
          ('AAA', DATE '2020-02-01');
        INSERT INTO bronze.eodhd_fundamental_balance_sheet_request VALUES
          ('AAA', 200, 1), ('BBB', 404, 0);
    """)
    result = audit(con, top=4)
    assert result["rows"] == 5
    assert result["unavailable_rows"] == 4
    assert result["by_reason"] == {
        "before_first_filing": 1,
        "no_successful_response": 1,
        "older_than_365_days": 1,
        "pit_issuer_total_available": 1,
        "ticker_identity_ambiguous": 1,
    }
    assert result["dates_with_fewer_than_10_available_issues"] == 2
    con.close()
