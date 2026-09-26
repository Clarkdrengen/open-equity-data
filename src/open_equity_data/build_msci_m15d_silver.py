"""Derive security share observations from locally archived MSCI M15D ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import io
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zipfile import ZipFile

import pandas as pd

from open_equity_data.db import connect


def parse_definition(line: str) -> tuple[int, str] | None:
    """Use MSCI's fixed dictionary columns; labels can contain single spaces."""
    if not line.startswith("#") or len(line) != 78:
        return None
    try:
        number = int(line[1:4])
    except ValueError:
        return None
    key = line[39:69].strip()
    metadata = line[70:].split()
    if len(metadata) != 3 or metadata[0] not in {"N", "S", "D"}:
        return None  # report title, not a field definition
    return number, key
REQUIRED = {
    "calc_date", "security_name", "msci_timeseries_code",
    "msci_issuer_code", "msci_security_code", "historical_GIMI_FIF",
    "historical_GIMI_DIF", "scap_foreign_inclusion_factor",
    "scap_number_of_shares_today", "scap_closing_number_of_shares",
}
COLUMNS = ["source_sha256", "source_row_number", "observation_date",
           "security_name", "msci_timeseries_code", "msci_issuer_code",
           "msci_security_code", "historical_gimi_fif_raw",
           "historical_gimi_dif_raw", "scap_fif_raw",
           "shares_today_raw", "closing_shares_raw", "shares_today",
           "closing_shares", "parse_status"]


def numeric(raw: str) -> float | None:
    if not raw:
        return None
    try:
        value = Decimal(raw)
        return float(value) if value.is_finite() else None
    except InvalidOperation:
        return None


def observations(archive_bytes: bytes, digest: str):
    with ZipFile(io.BytesIO(archive_bytes)) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) != 1 or members[0].file_size > 100_000_000:
            raise ValueError("Unexpected M15D archive member layout")
        with z.open(members[0]) as source:
            definitions: dict[int, str] = {}
            seen_data = False
            for line_number, raw in enumerate(source, 1):
                line = raw.decode("latin-1").rstrip("\r\n")
                if not seen_data and line.startswith("#") and len(line) == 78:
                    parsed = parse_definition(line)
                    if parsed:
                        number, key = parsed
                        if number in definitions:
                            raise ValueError("Duplicate M15D field number")
                        definitions[number] = key
                    continue
                if not line.startswith("|"):
                    continue  # separators and fixed-width format guide rows
                seen_data = True
                fields = line.split("|")[1:]
                if fields and not fields[-1].strip():
                    fields.pop()
                if not REQUIRED.issubset(definitions.values()) or len(definitions) != 17:
                    raise ValueError("Unexpected M15D dictionary; inspect locally")
                if len(fields) != 17:
                    raise ValueError(f"M15D data row {line_number}: {len(fields)} fields")
                item = {definitions[i]: value.strip() for i, value in enumerate(fields, 1)}
                day_raw = item["calc_date"]
                try:
                    day = datetime.strptime(day_raw, "%Y%m%d").date()
                except ValueError:
                    day = None
                today_raw = item["scap_number_of_shares_today"]
                closing_raw = item["scap_closing_number_of_shares"]
                today, closing = numeric(today_raw), numeric(closing_raw)
                status = ("invalid_date" if day is None else
                          "invalid_share_number" if (today_raw and today is None)
                          or (closing_raw and closing is None) else
                          "shares_present" if today is not None or closing is not None
                          else "no_shares")
                yield (digest, line_number, day, item["security_name"],
                       item["msci_timeseries_code"], item["msci_issuer_code"],
                       item["msci_security_code"], item["historical_GIMI_FIF"],
                       item["historical_GIMI_DIF"],
                       item["scap_foreign_inclusion_factor"], today_raw,
                       closing_raw, today, closing, status)
            if not definitions or not seen_data:
                raise ValueError("No M15D dictionary or data rows")


def insert_chunk(con, chunk: list[tuple]) -> None:
    con.register("m15d_chunk", pd.DataFrame(chunk, columns=COLUMNS))
    try:
        con.execute("INSERT INTO silver.msci_m15d_security_observation SELECT * FROM m15d_chunk")
    finally:
        con.unregister("m15d_chunk")


def build(con, rebuild: bool = False):
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.msci_m15d_security_observation (
            source_sha256 VARCHAR NOT NULL,
            source_row_number BIGINT NOT NULL,
            observation_date DATE,
            security_name VARCHAR,
            msci_timeseries_code VARCHAR,
            msci_issuer_code VARCHAR,
            msci_security_code VARCHAR,
            historical_gimi_fif_raw VARCHAR,
            historical_gimi_dif_raw VARCHAR,
            scap_fif_raw VARCHAR,
            shares_today_raw VARCHAR,
            closing_shares_raw VARCHAR,
            shares_today DOUBLE,
            closing_shares DOUBLE,
            parse_status VARCHAR NOT NULL,
            PRIMARY KEY (source_sha256, source_row_number)
        )
    """)
    sources = con.execute("""
        SELECT source_sha256 FROM bronze.msci_m15d_source_archive
        ORDER BY source_relative_path
    """).fetchall()
    results = Counter()
    completed = set() if rebuild else {
        row[0] for row in con.execute("""
            SELECT DISTINCT source_sha256 FROM silver.msci_m15d_security_observation
        """).fetchall()
    }
    for (digest,) in sources:
        if digest in completed:
            results["already_built"] += 1
            continue
        raw = bytes(con.execute("""
            SELECT raw_archive_bytes FROM bronze.msci_m15d_source_archive
            WHERE source_sha256 = ?
        """, [digest]).fetchone()[0])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Bronze M15D archive digest mismatch")
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM silver.msci_m15d_security_observation WHERE source_sha256 = ?", [digest])
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
            print(f"M15D extension archives parsed: {results['archives']}/{len(sources)}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        result = build(con, args.rebuild)
        dates = con.execute("""
            SELECT MIN(observation_date), MAX(observation_date),
                   COUNT(DISTINCT msci_security_code)
            FROM silver.msci_m15d_security_observation
        """).fetchone()
        overlap = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT m.observation_date AS date
                FROM silver.msci_m15d_security_observation m
            ) m JOIN (SELECT DISTINCT date FROM silver.research_universe_eligibility
                      WHERE primary_research_eligible_exchange) r USING (date)
        """).fetchone()[0]
    print("M15D parse counts:", dict(result))
    print("date_range, distinct_MSCI_security_codes:", dates)
    print("exact_dates_with_primary_exchange_prices:", overlap)
    print("MSCI codes are not yet mapped to project ISIN/security IDs;"
          " today/closing share timing and scale remain candidate evidence.")


if __name__ == "__main__":
    main()
