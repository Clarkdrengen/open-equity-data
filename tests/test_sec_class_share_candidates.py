from datetime import date

import duckdb

from open_equity_data import load_sec_class_share_candidates as loader


HTML = b"""
<xbrli:context id="class-a">
  <xbrli:entity><xbrli:segment>
    <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">
      us-gaap:CommonClassAMember
    </xbrldi:explicitMember>
  </xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
</xbrli:context>
<ix:nonNumeric name="dei:TradingSymbol" contextRef="class-a">AAA</ix:nonNumeric>
<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding"
    contextRef="class-a">123</ix:nonFraction>
"""


def test_failed_retry_preserves_processed_filing(tmp_path, monkeypatch):
    database = str(tmp_path / "shares.duckdb")
    con = duckdb.connect(database)
    con.execute("CREATE SCHEMA bronze; CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.multi_listed_common_equity_candidate
        (cik VARCHAR, overlap_start DATE)
    """)
    con.execute("""
        INSERT INTO silver.multi_listed_common_equity_candidate
        VALUES ('0000000001', DATE '2026-01-01')
    """)
    con.execute("""
        CREATE TABLE bronze.sec_submission_entity
        (cik VARCHAR, entity_name VARCHAR)
    """)
    con.execute("""
        INSERT INTO bronze.sec_submission_entity VALUES
        ('0000000001', 'Example Corp')
    """)
    con.close()

    filing = {
        "form": "10-Q",
        "filingDate": "2026-08-01",
        "accessionNumber": "0000000001-26-000001",
        "primaryDocument": "example.htm",
    }
    monkeypatch.setattr(loader, "connect", lambda: duckdb.connect(database))
    monkeypatch.setattr(loader, "all_filings", lambda cik: [filing])
    monkeypatch.setattr(
        loader,
        "get_filing_document",
        lambda **kwargs: {"content": HTML, "sha256": "original"},
    )
    loader.main()

    def failed_fetch(**kwargs):
        raise OSError("temporary SEC failure")

    monkeypatch.setattr(loader, "get_filing_document", failed_fetch)
    loader.main()

    con = duckdb.connect(database)
    assert con.execute("""
        SELECT trading_symbol, shares_outstanding, source_document_sha256
        FROM silver.sec_class_share_candidate
    """).fetchall() == [("AAA", 123.0, "original")]
    assert con.execute("""
        SELECT processing_status, source_document_sha256
        FROM silver.sec_class_share_filing_audit
    """).fetchall() == [("processed", "original")]
    con.close()
