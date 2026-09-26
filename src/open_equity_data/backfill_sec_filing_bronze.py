"""Backfill Bronze source documents for existing Silver SEC filing audits.

Uses the existing on-disk SEC filing cache when present and fetches missing
documents from their EDGAR archive URLs. Never rewrites Silver observations.
"""

from __future__ import annotations

from open_equity_data.db import connect
from open_equity_data.sec import get_filing_document
from open_equity_data.sec_filing_bronze import create_tables, retain_document


def main() -> None:
    con = connect()
    create_tables(con)
    rows = con.execute("""
        SELECT cik, accession_number, primary_document,
               form, filing_date, source_document_sha256
        FROM silver.sec_class_share_filing_audit
        WHERE processing_status = 'processed'
        ORDER BY cik, filing_date, accession_number
    """).fetchall()

    retained = 0
    missing = 0
    changed = 0
    errors = 0
    for i, (cik, accession, primary, form, filed, expected) in enumerate(rows, 1):
        if expected is None:
            missing += 1
            continue
        if con.execute("""
            SELECT 1 FROM bronze.sec_filing_document_observation
            WHERE cik = ? AND accession_number = ?
              AND primary_document = ? AND source_document_sha256 = ?
        """, [cik, accession, primary, expected]).fetchone():
            retained += 1
            continue
        try:
            document = get_filing_document(cik, accession, primary)
            if document["sha256"] != expected:
                changed += 1
                print(f"HASH MISMATCH {cik} {accession} {primary}", flush=True)
                continue
            con.execute("BEGIN TRANSACTION")
            try:
                retain_document(
                    con, cik=cik, accession_number=accession,
                    primary_document=primary, form=form,
                    filing_date=filed, document=document,
                )
                con.execute("COMMIT")
                retained += 1
            except Exception:
                con.execute("ROLLBACK")
                raise
        except Exception as exc:
            errors += 1
            print(f"ERROR {cik} {accession} {primary}: {exc}", flush=True)
        if i % 25 == 0 or i == len(rows):
            print(f"{i}/{len(rows)} retained={retained} "
                  f"missing_hash={missing} changed={changed} errors={errors}",
                  flush=True)

    print(f"Finished: audited={len(rows)} retained={retained} "
          f"missing_hash={missing} changed={changed} errors={errors}")
    con.close()


if __name__ == "__main__":
    main()
