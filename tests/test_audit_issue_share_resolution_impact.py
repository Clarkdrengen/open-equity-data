import duckdb

from open_equity_data.audit_issue_share_resolution_impact import audit


def test_audit_separates_actual_siblings_from_span_only_and_sec_future():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate (
            cik VARCHAR, security_id_a BIGINT, security_id_b BIGINT,
            overlap_start DATE, overlap_end DATE
        );
        CREATE TABLE silver.security_daily_shares_outstanding_pit (
            security_id BIGINT, ticker VARCHAR, date DATE,
            ticker_identity_ambiguous BOOLEAN, shares_pit_available BOOLEAN,
            shares_outstanding DOUBLE, shares_age_days INTEGER
        );
        CREATE TABLE silver.research_universe_eligibility (
            security_id BIGINT, date DATE,
            primary_research_eligible_exchange BOOLEAN
        );
        CREATE TABLE silver.sec_class_share_candidate (
            cik VARCHAR, trading_symbol VARCHAR, filing_date DATE,
            symbol_mapping_status VARCHAR
        );
        INSERT INTO silver.multi_listed_common_equity_candidate VALUES
          ('0001', 1, 2, DATE '2020-01-01', DATE '2020-01-03');
        INSERT INTO silver.security_daily_shares_outstanding_pit VALUES
          (1, 'AAA', DATE '2020-01-01', FALSE, TRUE, 100, 1),
          (2, 'BBB', DATE '2020-01-01', FALSE, FALSE, NULL, NULL),
          (1, 'AAA', DATE '2020-01-02', FALSE, TRUE, 100, 2),
          (1, 'AAA', DATE '2020-01-03', FALSE, TRUE, 100, 3),
          (2, 'BBB', DATE '2020-01-03', FALSE, FALSE, NULL, NULL),
          (3, 'CCC', DATE '2020-01-01', FALSE, TRUE, 300, 1),
          (4, 'DDD', DATE '2020-01-01', TRUE, FALSE, 400, 2);
        INSERT INTO silver.research_universe_eligibility VALUES
          (1, DATE '2020-01-01', TRUE),
          (2, DATE '2020-01-01', TRUE),
          (1, DATE '2020-01-02', TRUE),
          (1, DATE '2020-01-03', TRUE),
          (2, DATE '2020-01-03', TRUE);
        INSERT INTO silver.sec_class_share_candidate VALUES
          ('0001', 'AAA', DATE '2020-01-03', 'mapped_unique_symbol'),
          ('0001', 'BBB', DATE '2020-01-04', 'mapped_unique_symbol');
    """)
    result = audit(con, top=10)
    assert result["issue_days"] == 7
    assert result["detector_distinct_issues"] == 2
    assert result["exclusive_partitions"] == {
        "coobserved_multi_issue_candidate": 4,
        "span_only_multi_issue_candidate": 1,
        "eodhd_pit_other_issue_days": 1,
        "ticker_identity_ambiguous": 1,
    }
    assert result["candidate_days_by_sec_evidence"] == {
        "later_mapped_candidate_fact_only": 4,
        "mapped_candidate_fact_filed": 1,
    }
    assert result["eodhd_pit_status_all_partitions"] == {
        "available": 4,
        "missing": 2,
        "ticker_identity_ambiguous": 1,
    }
    con.close()
