import duckdb
import pandas as pd

from open_equity_data.audit_sec_class_mapping_impact import (
    audit,
    issuer_summary,
    issue_summary,
    missing_spans,
)


def test_impact_counts_same_day_pairs_and_keeps_unmapped_evidence_separate():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate AS
        SELECT '0001' AS cik, 1 AS security_id_a, 'A' AS ticker_a,
               2 AS security_id_b, 'B' AS ticker_b,
               DATE '2023-01-02' AS overlap_start,
               DATE '2023-01-04' AS overlap_end
    """)
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT * FROM (VALUES
            (1, 'A', DATE '2023-01-02', TRUE),
            (2, 'B', DATE '2023-01-02', TRUE),
            (1, 'A', DATE '2023-01-03', TRUE),
            (2, 'B', DATE '2023-01-03', TRUE),
            (1, 'A', DATE '2023-01-04', TRUE)
        ) AS v(security_id, ticker, date, primary_research_eligible_exchange)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT security_id, date, TRUE AS shares_pit_available
        FROM silver.research_universe_eligibility
    """)
    con.execute("""
        CREATE TABLE silver.sec_class_share_candidate AS
        SELECT * FROM (VALUES
            ('0001', 'Example', 'ClassA', DATE '2023-01-03', 'f1',
             DATE '2022-12-31', 'A', 'mapped_unique_symbol', 100.0),
            ('0001', 'Example', 'ClassB', DATE '2023-01-02', 'f0',
             DATE '2022-12-31', NULL, 'no_trading_symbol', 200.0)
        ) AS v(cik, entity_name, class_member, filing_date,
               accession_number, shares_as_of_date, trading_symbol,
               symbol_mapping_status, shares_outstanding)
    """)
    con.execute("""
        CREATE TABLE silver.sec_class_share_filing_audit AS
        SELECT 'success' AS processing_status
    """)

    daily, unmapped, summary = audit(con)
    assert len(daily) == 4  # the unmatched final day is not a paired date
    assert summary["daily_evidence_status_rows"] == {
        "before_first_mapped_filing": 1,
        "mapped_fact_filed_by_date": 1,
        "no_same_filing_symbol_fact_for_ticker": 2,
    }
    assert summary["unmapped_source_fact_status"] == {"no_symbol_evidence": 1}
    assert summary["eodhd_pit_available_on_candidate_rows"] == 4
    assert unmapped.iloc[0]["class_member"] == "ClassB"
    assert issue_summary(daily).set_index("ticker").loc["A", "candidate_days"] == 2
    assert issuer_summary(daily).iloc[0]["candidate_issue_days"] == 4
    spans = missing_spans(daily)
    assert set(spans["first_date"]) == {pd.Timestamp("2023-01-02")}
