"""Extract dated share and price evidence from local M15D/M15E RIF Bronze ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import io
from collections import Counter
from datetime import datetime
from zipfile import ZipFile

import pandas as pd

from open_equity_data.build_msci_m15d_silver import numeric, parse_definition
from open_equity_data.db import connect


REQUIRED = {
    "calc_date", "security_name", "msci_timeseries_code", "msci_issuer_code",
    "msci_security_code", "isin", "price", "price_ISO_currency_symbol",
    "eod_number_of_shares_today", "eod_number_of_shares_next_day",
    "closing_number_of_shares",
}
COLUMNS = [
    "source_sha256", "source_row_number", "observation_date", "security_name",
    "msci_timeseries_code", "msci_issuer_code", "msci_security_code", "isin",
    "price_currency", "price_raw", "price", "shares_today_raw",
    "shares_next_day_raw", "closing_shares_raw", "shares_today",
    "shares_next_day", "closing_shares", "closing_cap_usd_raw", "parse_status",
]


def observations(archive_bytes: bytes, digest: str):
    with ZipFile(io.BytesIO(archive_bytes)) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) != 1 or members[0].file_size > 100_000_000:
            raise ValueError("Unexpected MSCI RIF archive member layout")
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
                            raise ValueError("Duplicate RIF dictionary field")
                        definitions[number] = key
                    continue
                if not line.startswith("|"):
                    continue
                seen_data = True
                if not REQUIRED.issubset(definitions.values()):
                    missing = sorted(REQUIRED - set(definitions.values()))
                    raise ValueError(f"RIF share dictionary missing fields: {missing}")
                if sorted(definitions) != list(range(1, len(definitions) + 1)):
                    raise ValueError("Non-contiguous RIF dictionary")
                fields = line.split("|")[1:]
                if len(fields) == len(definitions) + 1 and not fields[-1].strip():
                    fields.pop()
                if len(fields) != len(definitions):
                    raise ValueError(f"RIF data row {line_number}: field/dictionary mismatch")
                item = {definitions[i]: value.strip() for i, value in enumerate(fields, 1)}
                try:
                    day = datetime.strptime(item["calc_date"], "%Y%m%d").date()
                except ValueError:
                    day = None
                today_raw = item["eod_number_of_shares_today"]
                next_raw = item["eod_number_of_shares_next_day"]
                closing_raw = item["closing_number_of_shares"]
                price_raw = item["price"]
                today, next_day, closing = (
                    numeric(today_raw), numeric(next_raw), numeric(closing_raw)
                )
                price = numeric(price_raw)
                status = ("invalid_date" if day is None else
                          "invalid_number" if any(
                              raw and value is None for raw, value in (
                                  (today_raw, today), (next_raw, next_day),
                                  (closing_raw, closing), (price_raw, price)
                              )
                          ) else
                          "shares_present" if any(
                              value is not None and value > 0
                              for value in (today, next_day, closing)
                          ) else "no_shares")
                yield (
                    digest, line_number, day, item["security_name"],
                    item["msci_timeseries_code"], item["msci_issuer_code"],
                    item["msci_security_code"], item["isin"].upper().strip(),
                    item["price_ISO_currency_symbol"], price_raw, price,
                    today_raw, next_raw, closing_raw, today, next_day, closing,
                    item.get("unadj_market_cap_today_usdol", ""), status,
                )
            if not seen_data:
                raise ValueError("No RIF data rows")


def build(con, family: str = "m15d", rebuild: bool = False):
    if family not in {"m15d", "m15e"}:
        raise ValueError("Unknown MSCI source family")
    source = f"bronze.msci_{family}_rif_source_archive"
    target = f"silver.msci_{family}_rif_share_observation"
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {target} (
            source_sha256 VARCHAR NOT NULL,
            source_row_number BIGINT NOT NULL,
            observation_date DATE,
            security_name VARCHAR,
            msci_timeseries_code VARCHAR,
            msci_issuer_code VARCHAR,
            msci_security_code VARCHAR,
            isin VARCHAR,
            price_currency VARCHAR,
            price_raw VARCHAR,
            price DOUBLE,
            shares_today_raw VARCHAR,
            shares_next_day_raw VARCHAR,
            closing_shares_raw VARCHAR,
            shares_today DOUBLE,
            shares_next_day DOUBLE,
            closing_shares DOUBLE,
            closing_cap_usd_raw VARCHAR,
            parse_status VARCHAR NOT NULL,
            PRIMARY KEY (source_sha256, source_row_number)
        )
    """)
    digests = con.execute(f"""
        SELECT source_sha256 FROM {source} ORDER BY source_relative_path
    """).fetchall()
    done = set() if rebuild else {
        row[0] for row in con.execute(
            f"SELECT DISTINCT source_sha256 FROM {target}"
        ).fetchall()
    }
    counts = Counter()
    for (digest,) in digests:
        if digest in done:
            counts["already_built"] += 1
            continue
        raw = bytes(con.execute(
            f"SELECT raw_archive_bytes FROM {source} WHERE source_sha256 = ?",
            [digest],
        ).fetchone()[0])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Bronze RIF archive digest mismatch")
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(f"DELETE FROM {target} WHERE source_sha256 = ?", [digest])
            chunk = []
            for row in observations(raw, digest):
                chunk.append(row)
                counts[row[-1]] += 1
                if len(chunk) >= 10_000:
                    con.register("rif_share_chunk", pd.DataFrame(chunk, columns=COLUMNS))
                    try:
                        con.execute(f"INSERT INTO {target} SELECT * FROM rif_share_chunk")
                    finally:
                        con.unregister("rif_share_chunk")
                    chunk.clear()
            if chunk:
                con.register("rif_share_chunk", pd.DataFrame(chunk, columns=COLUMNS))
                try:
                    con.execute(f"INSERT INTO {target} SELECT * FROM rif_share_chunk")
                finally:
                    con.unregister("rif_share_chunk")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        counts["archives"] += 1
        if counts["archives"] % 20 == 0:
            print(f"{family.upper()} RIF share archives parsed: {counts['archives']}/{len(digests)}", flush=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["m15d", "m15e"], default="m15d")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        counts = build(con, args.family, args.rebuild)
    print(f"{args.family.upper()} RIF share parse counts:", dict(counts))


if __name__ == "__main__":
    main()
