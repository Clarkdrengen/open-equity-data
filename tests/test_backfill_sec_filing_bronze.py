import hashlib

import duckdb
import pytest

from open_equity_data import backfill_sec_filing_bronze as backfill
from open_equity_data.sec import FILINGS_CACHE_DIR


def test_cache_path_does_not_change_with_working_directory(tmp_path, monkeypatch):
    before = FILINGS_CACHE_DIR.resolve()
    monkeypatch.chdir(tmp_path)
    assert FILINGS_CACHE_DIR.resolve() == before


def test_backfill_stops_after_three_mismatches_without_bronze_rows(
    tmp_path, monkeypatch, capsys
):
    path = str(tmp_path / "sample.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.sec_class_share_filing_audit (
            cik VARCHAR, accession_number VARCHAR, primary_document VARCHAR,
            form VARCHAR, filing_date DATE, source_document_sha256 VARCHAR,
            processing_status VARCHAR
        )
    """)
    con.executemany("""
        INSERT INTO silver.sec_class_share_filing_audit
        VALUES ('0000000001', ?, 'report.htm', '10-Q', DATE '2019-05-10', ?, 'processed')
    """, [(f"0000000001-19-{n:06d}", "0" * 64) for n in range(3)])
    con.close()

    monkeypatch.setattr(backfill, "connect", lambda: duckdb.connect(path))
    monkeypatch.setattr(backfill, "get_filing_document", lambda *args: {
        "content": b"other source bytes",
        "sha256": hashlib.sha256(b"other source bytes").hexdigest(),
        "source_access": "local_cache",
        "cache_path": "/example/report.htm",
    })
    with pytest.raises(SystemExit) as stopped:
        backfill.main()
    assert stopped.value.code == 2
    assert "STOPPED after three consecutive mismatches" in capsys.readouterr().out

    con = duckdb.connect(path)
    assert con.execute("SELECT COUNT(*) FROM bronze.sec_filing_document").fetchone() == (0,)
    con.close()
