"""Archive an externally supplied MSCI CSV byte-for-byte in Bronze."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from open_equity_data.db import connect


def archive(con, path: Path) -> str:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze.msci_usa_source_file (
            source_sha256 VARCHAR PRIMARY KEY,
            source_filename VARCHAR NOT NULL,
            source_origin VARCHAR NOT NULL,
            byte_count BIGINT NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            raw_file_bytes BLOB NOT NULL
        )
    """)
    existing = con.execute(
        "SELECT raw_file_bytes FROM bronze.msci_usa_source_file WHERE source_sha256 = ?",
        [digest],
    ).fetchone()
    if existing is not None:
        if bytes(existing[0]) != raw:
            raise ValueError("Stored Bronze bytes differ from matching SHA-256")
        return digest
    con.execute("""
        INSERT INTO bronze.msci_usa_source_file
        SELECT ?, ?, 'user_supplied_local_file', ?, current_timestamp, ?
    """, [digest, path.name, len(raw), raw])
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msci-csv", type=Path, required=True)
    args = parser.parse_args()
    with connect() as con:
        digest = archive(con, args.msci_csv)
    print(f"Bronze source SHA-256: {digest}")


if __name__ == "__main__":
    main()
