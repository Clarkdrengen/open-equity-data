"""Derive MSCI-code/ISIN observations from locally archived M15D RIF ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import io
from collections import Counter
from datetime import datetime
from zipfile import ZipFile

import pandas as pd

from open_equity_data.audit_msci_isin_reconciliation import valid_isin
from open_equity_data.build_msci_m15d_silver import parse_definition
from open_equity_data.db import connect


REQUIRED = {"calc_date", "security_name", "msci_timeseries_code",
            "msci_issuer_code", "msci_security_code", "isin"}
COLUMNS = ["source_sha256", "source_row_number", "observation_date",
           "security_name", "msci_timeseries_code", "msci_issuer_code",
           "msci_security_code", "sedol", "raw_isin", "isin", "ric",
           "parse_status"]


def observations(raw_archive: bytes, digest: str):
    with ZipFile(io.BytesIO(raw_archive)) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) != 1 or members[0].file_size > 100_000_000:
            raise ValueError("Unexpected RIF archive member layout")
        with z.open(members[0]) as source:
            definitions = {}
            seen_data = False
            for line_number, raw in enumerate(source, 1):
                line = raw.decode("latin-1").rstrip("\r\n")
                if not seen_data and line.startswith("#") and len(line) == 78:
                    parsed = parse_definition(line)
                    if parsed:
                        number, key = parsed
                        if number in definitions:
                            raise ValueError("Duplicate RIF field number")
                        definitions[number] = key
                    continue
                if not line.startswith("|"):
                    continue
                seen_data = True
                fields = line.split("|")[1:]
                if len(fields) == len(definitions) + 1 and not fields[-1].strip():
                    fields.pop()
                if not REQUIRED.issubset(definitions.values()):
                    raise ValueError("Missing required RIF dictionary fields")
                if len(fields) != len(definitions) or sorted(definitions) != list(range(1, len(definitions) + 1)):
                    raise ValueError(f"RIF data row {line_number}: field/dictionary mismatch")
                item = {definitions[i]: value.strip() for i, value in enumerate(fields, 1)}
                try:
                    day = datetime.strptime(item["calc_date"], "%Y%m%d").date()
                except ValueError:
                    day = None
                raw_isin = item["isin"]
                isin = raw_isin.upper().strip()
                status = ("invalid_date" if day is None else
                          "blank_isin" if not isin else
                          "invalid_isin" if not valid_isin(isin) else
                          "valid_isin")
                yield (digest, line_number, day, item["security_name"],
                       item["msci_timeseries_code"], item["msci_issuer_code"],
                       item["msci_security_code"], item.get("sedol"), raw_isin,
                       isin, item.get("RIC"), status)
            if not seen_data:
                raise ValueError("No RIF data rows")


def insert_chunk(con, chunk):
    con.register("rif_chunk", pd.DataFrame(chunk, columns=COLUMNS))
    try:
        con.execute("INSERT INTO silver.msci_m15d_rif_observation SELECT * FROM rif_chunk")
    finally:
        con.unregister("rif_chunk")


def build(con, rebuild: bool = False):
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.msci_m15d_rif_observation (
            source_sha256 VARCHAR NOT NULL,
            source_row_number BIGINT NOT NULL,
            observation_date DATE,
            security_name VARCHAR,
            msci_timeseries_code VARCHAR,
            msci_issuer_code VARCHAR,
            msci_security_code VARCHAR,
            sedol VARCHAR,
            raw_isin VARCHAR,
            isin VARCHAR,
            ric VARCHAR,
            parse_status VARCHAR NOT NULL,
            PRIMARY KEY (source_sha256, source_row_number)
        )
    """)
    sources = con.execute("""
        SELECT source_sha256 FROM bronze.msci_m15d_rif_source_archive
        ORDER BY source_relative_path
    """).fetchall()
    results = Counter()
    completed = set() if rebuild else {
        row[0] for row in con.execute("""
            SELECT DISTINCT source_sha256 FROM silver.msci_m15d_rif_observation
        """).fetchall()
    }
    for (digest,) in sources:
        if digest in completed:
            results["already_built"] += 1
            continue
        raw = bytes(con.execute("""
            SELECT raw_archive_bytes FROM bronze.msci_m15d_rif_source_archive
            WHERE source_sha256 = ?
        """, [digest]).fetchone()[0])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Bronze RIF archive digest mismatch")
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM silver.msci_m15d_rif_observation WHERE source_sha256 = ?", [digest])
            chunk = []
            for row in observations(raw, digest):
                chunk.append(row)
                results[row[-1]] += 1
                if len(chunk) >= 10_000:
                    insert_chunk(con, chunk)
                    chunk = []
            if chunk:
                insert_chunk(con, chunk)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        results["archives"] += 1
        if results["archives"] % 20 == 0:
            print(f"M15D RIF archives parsed: {results['archives']}/{len(sources)}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        result = build(con, args.rebuild)
    print("M15D RIF parse counts:", dict(result))


if __name__ == "__main__":
    main()
