import hashlib
from datetime import date

import duckdb

from open_equity_data.load_sec_cover_page_share_candidates import create_tables, load
from open_equity_data.sec_filing_bronze import create_tables as create_bronze_tables
from open_equity_data.sec_filing_bronze import retain_document


def test_silver_candidate_replays_from_bronze_and_does_not_resolve_ticker():
    con = duckdb.connect(":memory:")
    create_bronze_tables(con)
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.sec_class_share_filing_audit (
          cik VARCHAR, accession_number VARCHAR, filing_date DATE,
          primary_document VARCHAR, source_document_sha256 VARCHAR,
          processing_status VARCHAR, class_share_fact_count BIGINT
        )
    """)
    html = b"""
      <p>Outstanding as of May 6, 2019</p>
      <table><tr><th>Class</th><th>Shares outstanding</th></tr>
        <tr><td>Class A Common Stock</td><td>28,212,301</td></tr>
      </table>
    """
    digest = hashlib.sha256(html).hexdigest()
    cik, accession, name = "0000000001", "0000000001-19-000001", "report.htm"
    retain_document(con, cik=cik, accession_number=accession,
                    primary_document=name, form="10-Q", filing_date="2019-05-10",
                    document={"content": html})
    con.execute("""
        INSERT INTO silver.sec_class_share_filing_audit
        VALUES (?, ?, DATE '2019-05-10', ?, ?, 'processed', 0)
    """, [cik, accession, name, digest])

    create_tables(con)
    result = load(con)
    assert result["candidate_rows"] == 1
    assert con.execute("""
        SELECT reported_class_label, shares_outstanding,
               shares_as_of_date, source_document_sha256, resolution_status
        FROM silver.sec_cover_page_share_candidate
    """).fetchall() == [
        ("Class A Common Stock", 28212301, date(2019, 5, 6),
         digest, "extracted_unreviewed")
    ]
    assert load(con)["already_audited"] == 1
    assert con.execute("SELECT COUNT(*) FROM silver.sec_cover_page_share_candidate").fetchone() == (1,)
    con.close()
