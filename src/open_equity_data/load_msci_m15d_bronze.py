"""Archive confidential M15D ZIPs byte-for-byte in local Bronze."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile

from open_equity_data.db import connect


def archive(con, root: Path) -> tuple[int, int]:
    files = sorted(p for p in root.rglob("*.zip")
                   if p.name.lower().endswith("m15d.extension.zip"))
    if not files:
        raise ValueError("No *m15d.extension.zip files found")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze.msci_m15d_source_archive (
            source_sha256 VARCHAR PRIMARY KEY,
            source_relative_path VARCHAR NOT NULL,
            source_origin VARCHAR NOT NULL,
            archive_byte_count BIGINT NOT NULL,
            member_name VARCHAR NOT NULL,
            member_byte_count BIGINT NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            raw_archive_bytes BLOB NOT NULL
        )
    """)
    added = 0
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        with ZipFile(path) as z:
            members = [m for m in z.infolist() if not m.is_dir()]
            if len(members) != 1 or members[0].file_size > 100_000_000:
                raise ValueError(f"Unexpected M15D archive member layout: {path}")
            member = members[0]
        existing = con.execute("""
            SELECT archive_byte_count FROM bronze.msci_m15d_source_archive
            WHERE source_sha256 = ?
        """, [digest]).fetchone()
        if existing:
            if existing[0] != len(raw):
                raise ValueError("Existing archive has inconsistent SHA-256/size")
            continue
        con.execute("""
            INSERT INTO bronze.msci_m15d_source_archive
            VALUES (?, ?, 'user_supplied_local_zip', ?, ?, ?, current_timestamp, ?)
        """, [digest, str(path.relative_to(root)), len(raw), member.filename,
              member.file_size, raw])
        added += 1
    return len(files), added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    with connect() as con:
        found, added = archive(con, args.directory)
    print(f"M15D ZIPs found={found} newly archived={added}")


if __name__ == "__main__":
    main()
