import hashlib

import duckdb
import pytest

from open_equity_data.sec_filing_bronze import (
    create_tables, read_retained_document, retain_document,
)


def test_document_versions_are_immutable_and_idempotent():
    con = duckdb.connect(":memory:")
    create_tables(con)
    params = dict(
        cik="0000000001", accession_number="0000000001-19-000001",
        primary_document="report.htm", form="10-Q", filing_date="2019-05-10",
    )
    first = b"original filing"
    second = b"changed source bytes"
    for body in (first, first, second):
        retain_document(con, **params, document={"content": body})

    assert con.execute("SELECT COUNT(*) FROM bronze.sec_filing_document").fetchone() == (2,)
    assert con.execute("""
        SELECT COUNT(*) FROM bronze.sec_filing_document_observation
    """).fetchone() == (2,)
    assert con.execute("""
        SELECT raw_document FROM bronze.sec_filing_document
        WHERE source_document_sha256 = ?
    """, [hashlib.sha256(first).hexdigest()]).fetchone() == (first,)
    assert read_retained_document(con, hashlib.sha256(first).hexdigest()) == first

    with pytest.raises(LookupError, match="absent"):
        read_retained_document(con, "not-present")

    with pytest.raises(ValueError, match="checksum"):
        retain_document(con, **params, document={"content": first, "sha256": "wrong"})
    with pytest.raises(ValueError, match="URL"):
        retain_document(con, **params, document={"content": first, "url": "https://elsewhere"})
    con.close()
