"""Parse archived MSCI CSV bytes into an auditable Silver observation table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
from datetime import date

import pandas as pd

from open_equity_data.audit_msci_isin_reconciliation import valid_isin
from open_equity_data.db import connect


COLUMNS = ["source_sha256", "source_row_number", "source_index", "raw_date",
           "raw_isin", "raw_company_name", "raw_mktcap", "field_count",
           "observation_date", "isin", "mktcap_as_supplied", "parse_status"]


def parsed_rows(raw: bytes, digest: str):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if next(reader, None) != ["", "Date", "ISIN", "CompanyName", "MktCap"]:
        raise ValueError("Unexpected MSCI CSV header; Bronze bytes are retained")
    for row_no, fields in enumerate(reader, 2):
        source_index = fields[0] if fields else None
        raw_date = fields[1] if len(fields) > 1 else None
        raw_isin = fields[2] if len(fields) > 2 else None
        name = ",".join(fields[3:-1]) if len(fields) >= 5 else None
        raw_cap = fields[-1] if len(fields) >= 5 else None
        day = None
        cap = None
        try:
            day = date.fromisoformat(raw_date or "")
            cap = float(raw_cap or "")
        except ValueError:
            pass
        isin = (raw_isin or "").strip().upper()
        if len(fields) < 5:
            status = "unexpected_width"
        elif isin == "NA" and (name or "").strip() == "NA" and (raw_cap or "").strip() == "NA":
            status = "na_padding"
        elif day is None:
            status = "invalid_date_or_cap"
        elif cap is None:
            status = "invalid_date_or_cap"
        elif not isin:
            status = "blank_isin"
        elif not valid_isin(isin):
            status = "invalid_isin"
        else:
            status = "valid_isin"
        yield (digest, row_no, source_index, raw_date, raw_isin, name,
               raw_cap, len(fields), day, isin, cap, status)


def build(con, digest: str | None = None) -> tuple[str, int]:
    if digest is None:
        sources = con.execute("SELECT source_sha256 FROM bronze.msci_usa_source_file").fetchall()
        if len(sources) != 1:
            raise ValueError("Specify --source-sha256 when Bronze holds multiple source files")
        digest = sources[0][0]
    source = con.execute("""
        SELECT raw_file_bytes FROM bronze.msci_usa_source_file WHERE source_sha256 = ?
    """, [digest]).fetchone()
    if source is None:
        raise ValueError("Source SHA-256 is absent from Bronze")
    raw = bytes(source[0])
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Bronze source bytes do not match recorded SHA-256")
    # Validate before touching existing Silver data.
    rows = parsed_rows(raw, digest)
    first = next(rows, None)
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.msci_usa_observation (
            source_sha256 VARCHAR NOT NULL,
            source_row_number BIGINT NOT NULL,
            source_index VARCHAR,
            raw_date VARCHAR,
            raw_isin VARCHAR,
            raw_company_name VARCHAR,
            raw_mktcap VARCHAR,
            field_count INTEGER,
            observation_date DATE,
            isin VARCHAR,
            mktcap_as_supplied DOUBLE,
            parse_status VARCHAR NOT NULL,
            PRIMARY KEY (source_sha256, source_row_number)
        )
    """)
    count = 0
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM silver.msci_usa_observation WHERE source_sha256 = ?", [digest])
        chunk = [first] if first is not None else []
        for row in rows:
            chunk.append(row)
            if len(chunk) >= 25_000:
                count += insert_chunk(con, chunk)
                chunk = []
        if chunk:
            count += insert_chunk(con, chunk)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return digest, count


def insert_chunk(con, chunk: list[tuple]) -> int:
    frame = pd.DataFrame(chunk, columns=COLUMNS)
    con.register("msci_silver_chunk", frame)
    try:
        con.execute("INSERT INTO silver.msci_usa_observation SELECT * FROM msci_silver_chunk")
    finally:
        con.unregister("msci_silver_chunk")
    return len(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256")
    args = parser.parse_args()
    with connect() as con:
        digest, count = build(con, args.source_sha256)
    print(f"Silver observations: {count:,} from Bronze SHA-256 {digest}")


if __name__ == "__main__":
    main()
