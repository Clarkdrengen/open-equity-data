"""Derive auditable cover-page share candidates from Bronze SEC documents.

No ticker mapping, PIT carry-forward, or market-cap changes are made.
"""

from __future__ import annotations

import argparse
from collections import Counter

from open_equity_data.db import connect
from open_equity_data.sec_cover_page_shares import PARSER_VERSION, extract_cover_shares
from open_equity_data.sec_filing_bronze import read_retained_document


def create_tables(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.sec_cover_page_share_candidate (
            cik VARCHAR NOT NULL,
            accession_number VARCHAR NOT NULL,
            filing_date DATE NOT NULL,
            primary_document VARCHAR NOT NULL,
            shares_as_of_date DATE NOT NULL,
            series_label VARCHAR,
            reported_class_label VARCHAR NOT NULL,
            shares_outstanding BIGINT NOT NULL,
            source_document_sha256 VARCHAR NOT NULL,
            extraction_method VARCHAR NOT NULL,
            table_index INTEGER NOT NULL,
            row_index INTEGER NOT NULL,
            source_row_text VARCHAR NOT NULL,
            resolution_status VARCHAR NOT NULL
        );

        CREATE TABLE IF NOT EXISTS silver.sec_cover_page_share_extraction_audit (
            cik VARCHAR NOT NULL,
            accession_number VARCHAR NOT NULL,
            filing_date DATE NOT NULL,
            primary_document VARCHAR NOT NULL,
            source_document_sha256 VARCHAR NOT NULL,
            extraction_method VARCHAR NOT NULL,
            candidate_count INTEGER NOT NULL,
            processing_status VARCHAR NOT NULL,
            error_message VARCHAR
        );
    """)


def load(con, *, ciks: list[str] | None = None, limit: int | None = None) -> dict:
    where = "AND a.cik IN (" + ",".join("?" for _ in ciks) + ")" if ciks else ""
    query = f"""
        SELECT DISTINCT a.cik, a.accession_number, a.filing_date,
               a.primary_document, a.source_document_sha256
        FROM silver.sec_class_share_filing_audit a
        JOIN bronze.sec_filing_document_observation b
          ON b.cik = a.cik AND b.accession_number = a.accession_number
         AND b.primary_document = a.primary_document
         AND b.source_document_sha256 = a.source_document_sha256
        WHERE a.processing_status = 'processed'
          AND a.class_share_fact_count = 0 {where}
        ORDER BY a.cik, a.filing_date, a.accession_number
    """
    rows = con.execute(query, ciks or []).fetchall()
    if limit is not None:
        rows = rows[:limit]
    totals = Counter()
    for cik, accession, filed, primary, digest in rows:
        prior = con.execute("""
            SELECT processing_status FROM silver.sec_cover_page_share_extraction_audit
            WHERE cik = ? AND accession_number = ?
              AND source_document_sha256 = ? AND extraction_method = ?
        """, [cik, accession, digest, PARSER_VERSION]).fetchone()
        if prior and prior[0] in {"candidates", "no_candidate"}:
            totals["already_audited"] += 1
            continue
        try:
            body = read_retained_document(con, digest)
            candidates = extract_cover_shares(body)
            # A parser can produce candidates, but cannot approve identity.
            values = [(
                cik, accession, filed, primary, c.as_of_date,
                c.series_label, c.class_label, c.shares_outstanding,
                digest, PARSER_VERSION, c.table_index, c.row_index,
                c.source_row_text, "extracted_unreviewed"
            ) for c in candidates if c.shares_outstanding > 0 and c.as_of_date <= filed]
            rejected = len(candidates) - len(values)
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute("""
                    DELETE FROM silver.sec_cover_page_share_candidate
                    WHERE cik = ? AND accession_number = ?
                      AND extraction_method = ?
                """, [cik, accession, PARSER_VERSION])
                con.execute("""
                    DELETE FROM silver.sec_cover_page_share_extraction_audit
                    WHERE cik = ? AND accession_number = ?
                      AND extraction_method = ?
                """, [cik, accession, PARSER_VERSION])
                if values:
                    con.executemany("""
                        INSERT INTO silver.sec_cover_page_share_candidate
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, values)
                con.execute("""
                    INSERT INTO silver.sec_cover_page_share_extraction_audit
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [cik, accession, filed, primary, digest, PARSER_VERSION,
                      len(values), "candidates" if values else "no_candidate",
                      f"{rejected} invalid/out-of-range candidates" if rejected else None])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            totals["filings_with_candidates" if values else "no_candidate"] += 1
            totals["candidate_rows"] += len(values)
            totals["rejected_rows"] += rejected
        except Exception as exc:
            totals["errors"] += 1
            print(f"ERROR {cik} {accession}: {exc}", flush=True)
            con.execute("""
                DELETE FROM silver.sec_cover_page_share_extraction_audit
                WHERE cik = ? AND accession_number = ? AND extraction_method = ?
            """, [cik, accession, PARSER_VERSION])
            con.execute("""
                INSERT INTO silver.sec_cover_page_share_extraction_audit
                VALUES (?, ?, ?, ?, ?, ?, 0, 'error', ?)
            """, [cik, accession, filed, primary, digest, PARSER_VERSION, repr(exc)])
    totals["eligible_bronze_filings"] = len(rows)
    return dict(totals)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", action="append", help="Optional CIK; repeat for several")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--preview", type=int, default=12)
    args = parser.parse_args()
    con = connect()
    try:
        create_tables(con)
        result = load(con, ciks=args.cik, limit=args.limit)
        print("SEC cover-page candidate extraction:", result)
        for row in con.execute("""
            SELECT cik, processing_status, COUNT(*) AS filings,
                   SUM(candidate_count) AS candidates
            FROM silver.sec_cover_page_share_extraction_audit
            WHERE extraction_method = ?
            GROUP BY 1, 2 ORDER BY 1, 2
        """, [PARSER_VERSION]).fetchall():
            print(row)
        print("UNREVIEWED SOURCE ROW PREVIEW")
        for row in con.execute("""
            SELECT cik, filing_date, shares_as_of_date, series_label,
                   reported_class_label, shares_outstanding,
                   accession_number, source_row_text
            FROM silver.sec_cover_page_share_candidate
            WHERE extraction_method = ?
            ORDER BY cik, filing_date, table_index, row_index
            LIMIT ?
        """, [PARSER_VERSION, args.preview]).fetchall():
            print(row)
    finally:
        con.close()


if __name__ == "__main__":
    main()
