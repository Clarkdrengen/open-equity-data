from __future__ import annotations

import time
from collections import defaultdict
from datetime import timedelta

from bs4 import BeautifulSoup

from open_equity_data.db import connect
from open_equity_data.sec import (
    all_filings,
    get_filing_document,
)
from open_equity_data.sec_shares import (
    extract_context_metadata,
    extract_shares_outstanding_facts_from_html,
)


FORMS = {
    "10-Q",
    "10-K",
    "10-Q/A",
    "10-K/A",
}


def _tag_name(tag) -> str:
    return (
        tag.name.lower()
        if getattr(tag, "name", None)
        else ""
    )


def extract_class_security_metadata(
    html: bytes | str,
) -> list[dict]:
    """
    Extract class-member -> listed security metadata from
    SEC cover-page Inline XBRL.
    """

    if isinstance(html, bytes):
        html = html.decode(
            "utf-8",
            errors="ignore",
        )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    contexts = extract_context_metadata(
        soup
    )

    rows: dict[tuple, dict] = {}

    for tag in soup.find_all():
        name = tag.get("name")

        if name not in {
            "dei:TradingSymbol",
            "dei:Security12bTitle",
        }:
            continue

        if not _tag_name(tag).endswith(
            "nonnumeric"
        ):
            continue

        context_id = tag.get(
            "contextref"
        )

        context = contexts.get(
            context_id,
            {},
        )

        class_member = context.get(
            "class_member"
        )

        if class_member is None:
            continue

        key = (
            context_id,
            class_member,
        )

        row = rows.setdefault(
            key,
            {
                "context_id":
                    context_id,

                "class_member":
                    class_member,

                "trading_symbol":
                    None,

                "security_title":
                    None,
            },
        )

        value = tag.get_text(
            " ",
            strip=True,
        )

        if name == "dei:TradingSymbol":
            row["trading_symbol"] = (
                value.upper().strip()
                if value
                else None
            )

        elif name == "dei:Security12bTitle":
            row["security_title"] = (
                value.strip()
                if value
                else None
            )

    return list(
        rows.values()
    )


def create_tables(con) -> None:
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS silver;

        CREATE TABLE IF NOT EXISTS
            silver.sec_class_share_candidate
        (
            cik VARCHAR NOT NULL,
            entity_name VARCHAR,

            filing_date DATE NOT NULL,
            accession_number VARCHAR NOT NULL,
            form VARCHAR NOT NULL,
            primary_document VARCHAR NOT NULL,

            shares_as_of_date DATE,
            class_member VARCHAR NOT NULL,

            trading_symbol VARCHAR,
            security_title VARCHAR,

            shares_outstanding DOUBLE NOT NULL,

            taxonomy VARCHAR NOT NULL,
            concept VARCHAR NOT NULL,
            context_id VARCHAR,

            symbol_mapping_status VARCHAR NOT NULL,

            source_document_sha256 VARCHAR,
            source VARCHAR NOT NULL
        );

        CREATE TABLE IF NOT EXISTS
            silver.sec_class_share_filing_audit
        (
            cik VARCHAR NOT NULL,
            entity_name VARCHAR,

            filing_date DATE NOT NULL,
            accession_number VARCHAR NOT NULL,
            form VARCHAR NOT NULL,
            primary_document VARCHAR NOT NULL,

            metadata_class_count BIGINT,
            shares_fact_count BIGINT,
            class_share_fact_count BIGINT,
            mapped_candidate_count BIGINT,

            processing_status VARCHAR NOT NULL,
            error_message VARCHAR,

            source_document_sha256 VARCHAR
        );
    """)


def main() -> None:
    con = connect()

    create_tables(con)

    issuer_rows = con.execute("""
        WITH x AS (
            SELECT
                cik,
                MIN(overlap_start)
                    AS first_overlap
            FROM silver.multi_listed_common_equity_candidate
            GROUP BY cik
        )
        SELECT
            x.cik,
            e.entity_name,
            x.first_overlap
        FROM x
        LEFT JOIN bronze.sec_submission_entity e
          ON e.cik = x.cik
        ORDER BY x.cik
    """).fetchall()

    print(
        f"Candidate issuers: {len(issuer_rows)}"
    )

    # --------------------------------------------------------
    # Build filing work queue first so progress / ETA is real.
    #
    # Start ~18 months before first simultaneous-listed period
    # to provide a PIT seed observation where possible.
    # --------------------------------------------------------

    work = []

    for i, (
        cik,
        entity_name,
        first_overlap,
    ) in enumerate(
        issuer_rows,
        start=1,
    ):
        start_date = (
            first_overlap
            - timedelta(days=550)
        )

        print(
            f"Discovering filings "
            f"[{i}/{len(issuer_rows)}] "
            f"{cik} {entity_name}",
            flush=True,
        )

        filings = all_filings(cik)

        seen_accessions = set()

        for filing in filings:
            form = filing.get("form")
            filing_date = filing.get(
                "filingDate"
            )
            accession = filing.get(
                "accessionNumber"
            )
            primary_document = filing.get(
                "primaryDocument"
            )

            if form not in FORMS:
                continue

            if not (
                filing_date
                and accession
                and primary_document
            ):
                continue

            if accession in seen_accessions:
                continue

            seen_accessions.add(
                accession
            )

            if filing_date < start_date.isoformat():
                continue

            work.append(
                {
                    "cik":
                        cik,

                    "entity_name":
                        entity_name,

                    "filing_date":
                        filing_date,

                    "accession_number":
                        accession,

                    "form":
                        form,

                    "primary_document":
                        primary_document,
                }
            )

    work.sort(
        key=lambda x: (
            x["cik"],
            x["filing_date"],
            x["accession_number"],
        )
    )

    print()
    print(
        f"Historical filings to process: "
        f"{len(work)}"
    )
    print()

    started = time.time()

    for n, item in enumerate(
        work,
        start=1,
    ):
        t0 = time.time()

        cik = item["cik"]
        entity_name = item[
            "entity_name"
        ]
        filing_date = item[
            "filing_date"
        ]
        accession = item[
            "accession_number"
        ]
        form = item["form"]
        primary_document = item[
            "primary_document"
        ]

        elapsed = time.time() - started

        if n > 1:
            rate = elapsed / (n - 1)
            eta = rate * (
                len(work) - n + 1
            )
            eta_text = (
                f"{eta / 60:.1f}m"
                if eta >= 60
                else f"{eta:.0f}s"
            )
        else:
            eta_text = "estimating"

        print(
            f"[{n}/{len(work)}] "
            f"{cik} {filing_date} "
            f"{form} "
            f"ETA {eta_text}",
            flush=True,
        )

        # Restartable Silver interpretation:
        # replace only this filing's derived rows.
        con.execute("""
            DELETE FROM
                silver.sec_class_share_candidate
            WHERE cik = ?
              AND accession_number = ?
        """, [
            cik,
            accession,
        ])

        con.execute("""
            DELETE FROM
                silver.sec_class_share_filing_audit
            WHERE cik = ?
              AND accession_number = ?
        """, [
            cik,
            accession,
        ])

        try:
            document = get_filing_document(
                cik=cik,
                accession_number=accession,
                primary_document=
                    primary_document,
            )

            html = document["content"]
            sha256 = document["sha256"]

            metadata = (
                extract_class_security_metadata(
                    html
                )
            )

            facts = (
                extract_shares_outstanding_facts_from_html(
                    html=html,
                    cik=cik,
                    filing_date=
                        filing_date,
                    accession_number=
                        accession,
                    form=form,
                    primary_document=
                        primary_document,
                )
            )

            # ------------------------------------------------
            # Resolve class member -> security metadata
            # only within THIS filing.
            # ------------------------------------------------

            metadata_by_member = defaultdict(
                list
            )

            for row in metadata:
                metadata_by_member[
                    row["class_member"]
                ].append(row)

            candidate_rows = []

            class_facts = [
                fact
                for fact in facts
                if fact.class_member
                is not None
                and fact.shares_outstanding
                is not None
                and fact.shares_outstanding
                > 0
            ]

            for fact in class_facts:
                matches = (
                    metadata_by_member.get(
                        fact.class_member,
                        [],
                    )
                )

                symbols = sorted({
                    row["trading_symbol"]
                    for row in matches
                    if row[
                        "trading_symbol"
                    ]
                })

                titles = sorted({
                    row["security_title"]
                    for row in matches
                    if row[
                        "security_title"
                    ]
                })

                if len(symbols) == 1:
                    trading_symbol = (
                        symbols[0]
                    )
                    status = (
                        "mapped_unique_symbol"
                    )

                elif len(symbols) == 0:
                    trading_symbol = None
                    status = (
                        "no_trading_symbol"
                    )

                else:
                    trading_symbol = None
                    status = (
                        "ambiguous_trading_symbol"
                    )

                security_title = (
                    titles[0]
                    if len(titles) == 1
                    else None
                )

                candidate_rows.append(
                    (
                        cik,
                        entity_name,
                        filing_date,
                        accession,
                        form,
                        primary_document,
                        fact.shares_as_of_date,
                        fact.class_member,
                        trading_symbol,
                        security_title,
                        float(
                            fact.shares_outstanding
                        ),
                        fact.taxonomy,
                        fact.concept,
                        fact.context_id,
                        status,
                        sha256,
                        "sec_inline_xbrl",
                    )
                )

            if candidate_rows:
                con.executemany("""
                    INSERT INTO
                        silver.sec_class_share_candidate
                    (
                        cik,
                        entity_name,
                        filing_date,
                        accession_number,
                        form,
                        primary_document,
                        shares_as_of_date,
                        class_member,
                        trading_symbol,
                        security_title,
                        shares_outstanding,
                        taxonomy,
                        concept,
                        context_id,
                        symbol_mapping_status,
                        source_document_sha256,
                        source
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?
                    )
                """, candidate_rows)

            mapped_count = sum(
                1
                for row in candidate_rows
                if row[14]
                == "mapped_unique_symbol"
            )

            con.execute("""
                INSERT INTO
                    silver.sec_class_share_filing_audit
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
            """, [
                cik,
                entity_name,
                filing_date,
                accession,
                form,
                primary_document,
                len(metadata),
                len(facts),
                len(class_facts),
                mapped_count,
                "processed",
                None,
                sha256,
            ])

            print(
                f"    metadata={len(metadata)} "
                f"class_facts={len(class_facts)} "
                f"mapped={mapped_count} "
                f"{time.time() - t0:.1f}s",
                flush=True,
            )

        except Exception as exc:
            con.execute("""
                INSERT INTO
                    silver.sec_class_share_filing_audit
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
            """, [
                cik,
                entity_name,
                filing_date,
                accession,
                form,
                primary_document,
                0,
                0,
                0,
                0,
                "error",
                repr(exc),
                None,
            ])

            print(
                f"    ERROR: {exc!r}",
                flush=True,
            )

    print()
    print(
        f"Finished in "
        f"{(time.time() - started) / 60:.1f}m"
    )

    con.close()


if __name__ == "__main__":
    main()
