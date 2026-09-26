"""Retain exact SEC filing documents before deriving class-share evidence."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from open_equity_data.sec import ARCHIVES_BASE_URL, normalize_cik


def create_tables(con) -> None:
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS bronze;

        CREATE TABLE IF NOT EXISTS bronze.sec_filing_document (
            source_document_sha256 VARCHAR PRIMARY KEY,
            raw_document BLOB NOT NULL,
            content_length_bytes BIGINT NOT NULL,
            first_ingested_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bronze.sec_filing_document_observation (
            cik VARCHAR NOT NULL,
            accession_number VARCHAR NOT NULL,
            primary_document VARCHAR NOT NULL,
            source_document_sha256 VARCHAR NOT NULL,
            form VARCHAR NOT NULL,
            filing_date DATE NOT NULL,
            source_url VARCHAR NOT NULL,
            source_system VARCHAR NOT NULL,
            source_access VARCHAR NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            PRIMARY KEY (
                cik, accession_number, primary_document,
                source_document_sha256
            )
        );
    """)


def filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    return (
        f"{ARCHIVES_BASE_URL}/{int(normalize_cik(cik))}/"
        f"{accession_number.replace('-', '')}/{primary_document}"
    )


def retain_document(
    con,
    *,
    cik: str,
    accession_number: str,
    primary_document: str,
    form: str,
    filing_date: str | date,
    document: dict,
) -> str:
    """Append a source version; reject mismatched bytes or source identity."""
    body = document["content"]
    digest = hashlib.sha256(body).hexdigest()
    if document.get("sha256", digest) != digest:
        raise ValueError("SEC document checksum does not match its bytes")

    url = filing_url(cik, accession_number, primary_document)
    if document.get("url", url) != url:
        raise ValueError("SEC document URL does not match filing identity")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if con.execute("""
        SELECT 1 FROM bronze.sec_filing_document
        WHERE source_document_sha256 = ?
    """, [digest]).fetchone() is None:
        con.execute("""
            INSERT INTO bronze.sec_filing_document VALUES (?, ?, ?, ?)
        """, [digest, body, len(body), now])

    if con.execute("""
        SELECT 1 FROM bronze.sec_filing_document_observation
        WHERE cik = ? AND accession_number = ?
          AND primary_document = ? AND source_document_sha256 = ?
    """, [cik, accession_number, primary_document, digest]).fetchone() is None:
        con.execute("""
            INSERT INTO bronze.sec_filing_document_observation
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            cik, accession_number, primary_document, digest,
            form, filing_date, url, "SEC EDGAR Archives",
            document.get("source_access", "local_cache_or_archive"), now,
        ])
    return digest
