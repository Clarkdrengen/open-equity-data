import argparse
import hashlib
from datetime import date

from open_equity_data.db import connect
from open_equity_data.sec import get_filing_document


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--from-ticker", required=True)
    parser.add_argument("--to-ticker", required=True)
    parser.add_argument("--cik", required=True)
    parser.add_argument("--effective-date", required=True)
    parser.add_argument("--accession", required=True)
    parser.add_argument("--document", required=True)
    parser.add_argument(
        "--relationship-type",
        default="ticker_change",
    )
    parser.add_argument(
        "--same-issuer",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--same-security",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    args = parser.parse_args()

    filing = get_filing_document(
        args.cik,
        args.accession,
        args.document,
    )

    evidence_id = hashlib.sha256(
        "|".join([
            "SEC",
            args.cik,
            args.from_ticker,
            args.to_ticker,
            args.effective_date,
            args.accession,
            args.document,
        ]).encode()
    ).hexdigest()

    con = connect()

    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.ticker_transition_evidence (
            evidence_id VARCHAR PRIMARY KEY,
            from_ticker VARCHAR,
            to_ticker VARCHAR,
            cik VARCHAR,
            effective_date DATE,
            relationship_type VARCHAR,
            same_issuer BOOLEAN,
            same_security BOOLEAN,
            source_type VARCHAR,
            source_reference VARCHAR,
            accession_number VARCHAR,
            primary_document VARCHAR,
            source_sha256 VARCHAR,
            validation_method VARCHAR,
            evidence_strength VARCHAR,
            loaded_at TIMESTAMP
        )
    """)

    con.execute("""
        INSERT OR REPLACE INTO silver.ticker_transition_evidence
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            'SEC_8K',
            ?, ?, ?, ?,
            'manual_primary_source_review',
            'primary_source',
            CURRENT_TIMESTAMP
        )
    """, [
        evidence_id,
        args.from_ticker,
        args.to_ticker,
        args.cik,
        date.fromisoformat(args.effective_date),
        args.relationship_type,
        args.same_issuer,
        args.same_security,
        filing["url"],
        args.accession,
        args.document,
        filing["sha256"],
    ])

    print(
        f"Stored: {args.from_ticker} -> {args.to_ticker} "
        f"effective {args.effective_date}"
    )
    print("Evidence ID:", evidence_id)
    print("Source:", filing["url"])

    con.close()


if __name__ == "__main__":
    main()
