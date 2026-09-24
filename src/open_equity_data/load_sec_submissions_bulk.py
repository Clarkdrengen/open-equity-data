"""
Load the SEC bulk submissions archive into Bronze.

Source:
    https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip

The archive contains one JSON submission file per SEC filer. We retain
identity metadata needed for historical security -> CIK resolution.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

import httpx

from open_equity_data.db import connect
from open_equity_data.sec import _headers


URL = (
    "https://www.sec.gov/Archives/edgar/"
    "daily-index/bulkdata/submissions.zip"
)


def main() -> None:
    print("Downloading SEC submissions.zip...", flush=True)

    chunks = []
    downloaded = 0

    with httpx.Client(
        headers=_headers(),
        timeout=120.0,
        follow_redirects=True,
    ) as client:
        with client.stream("GET", URL) as response:
            response.raise_for_status()

            content_length = response.headers.get(
                "Content-Length"
            )

            total_bytes = (
                int(content_length)
                if content_length
                else None
            )

            next_report_mb = 5

            for chunk in response.iter_bytes(
                chunk_size=1024 * 1024
            ):
                chunks.append(chunk)
                downloaded += len(chunk)

                downloaded_mb = (
                    downloaded / 1024 / 1024
                )

                if downloaded_mb >= next_report_mb:
                    if total_bytes:
                        total_mb = (
                            total_bytes / 1024 / 1024
                        )

                        pct = (
                            downloaded
                            / total_bytes
                        )

                        print(
                            f"  downloaded "
                            f"{downloaded_mb:.1f}/"
                            f"{total_mb:.1f} MB "
                            f"({pct:.1%})",
                            flush=True,
                        )
                    else:
                        print(
                            f"  downloaded "
                            f"{downloaded_mb:.1f} MB",
                            flush=True,
                        )

                    next_report_mb += 5

    content = b"".join(chunks)

    print(
        f"Download complete: "
        f"{len(content) / 1024 / 1024:.1f} MB",
        flush=True,
    )

    zf = zipfile.ZipFile(
        io.BytesIO(content)
    )

    names = [
        n
        for n in zf.namelist()
        if n.startswith("CIK")
        and n.endswith(".json")
    ]

    print(
        f"Filer JSON files: {len(names):,}",
        flush=True,
    )

    con = connect()

    con.execute("""
        CREATE SCHEMA IF NOT EXISTS bronze
    """)

    con.execute("""
        DROP TABLE IF EXISTS bronze.sec_submission_entity
    """)

    con.execute("""
        CREATE TABLE bronze.sec_submission_entity (
            cik VARCHAR,
            entity_name VARCHAR,
            entity_type VARCHAR,
            sic VARCHAR,
            sic_description VARCHAR,
            owner_org VARCHAR,
            fiscal_year_end VARCHAR,
            state_of_incorporation VARCHAR,
            state_of_incorporation_description VARCHAR,
            phone VARCHAR,
            flags VARCHAR,
            insider_transaction_for_owner_exists BOOLEAN,
            insider_transaction_for_issuer_exists BOOLEAN,
            retrieved_at TIMESTAMP
        )
    """)

    con.execute("""
        DROP TABLE IF EXISTS bronze.sec_submission_ticker
    """)

    con.execute("""
        CREATE TABLE bronze.sec_submission_ticker (
            cik VARCHAR,
            ticker VARCHAR,
            exchange VARCHAR,
            retrieved_at TIMESTAMP
        )
    """)

    con.execute("""
        DROP TABLE IF EXISTS bronze.sec_submission_former_name
    """)

    con.execute("""
        CREATE TABLE bronze.sec_submission_former_name (
            cik VARCHAR,
            former_name VARCHAR,
            from_date DATE,
            to_date DATE,
            retrieved_at TIMESTAMP
        )
    """)

    retrieved_at = datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )

    entity_rows = []
    ticker_rows = []
    former_name_rows = []

    batch_size = 5000

    for i, name in enumerate(
        names,
        start=1,
    ):
        data = json.loads(
            zf.read(name)
        )

        cik = str(
            data.get("cik", "")
        ).zfill(10)

        entity_rows.append(
            (
                cik,
                data.get("name"),
                data.get("entityType"),
                data.get("sic"),
                data.get("sicDescription"),
                data.get("ownerOrg"),
                data.get("fiscalYearEnd"),
                data.get("stateOfIncorporation"),
                data.get(
                    "stateOfIncorporationDescription"
                ),
                data.get("phone"),
                data.get("flags"),
                data.get(
                    "insiderTransactionForOwnerExists"
                ),
                data.get(
                    "insiderTransactionForIssuerExists"
                ),
                retrieved_at,
            )
        )

        tickers = data.get(
            "tickers",
            [],
        )

        exchanges = data.get(
            "exchanges",
            [],
        )

        for j, ticker in enumerate(
            tickers
        ):
            exchange = (
                exchanges[j]
                if j < len(exchanges)
                else None
            )

            ticker_rows.append(
                (
                    cik,
                    ticker,
                    exchange,
                    retrieved_at,
                )
            )

        for former in data.get(
            "formerNames",
            [],
        ):
            former_name_rows.append(
                (
                    cik,
                    former.get("name"),
                    former.get("from"),
                    former.get("to"),
                    retrieved_at,
                )
            )

        if (
            len(entity_rows)
            >= batch_size
        ):
            con.executemany(
                """
                INSERT INTO bronze.sec_submission_entity
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entity_rows,
            )

            entity_rows.clear()

        if (
            len(ticker_rows)
            >= batch_size
        ):
            con.executemany(
                """
                INSERT INTO bronze.sec_submission_ticker
                VALUES (?, ?, ?, ?)
                """,
                ticker_rows,
            )

            ticker_rows.clear()

        if (
            len(former_name_rows)
            >= batch_size
        ):
            con.executemany(
                """
                INSERT INTO bronze.sec_submission_former_name
                VALUES (?, ?, ?, ?, ?)
                """,
                former_name_rows,
            )

            former_name_rows.clear()

        if i % 100 == 0 or i == len(names):
            print(
                f"Processed {i:,}/{len(names):,} "
                f"({i / len(names):.1%})",
                flush=True,
            )

    if entity_rows:
        con.executemany(
            """
            INSERT INTO bronze.sec_submission_entity
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            entity_rows,
        )

    if ticker_rows:
        con.executemany(
            """
            INSERT INTO bronze.sec_submission_ticker
            VALUES (?, ?, ?, ?)
            """,
            ticker_rows,
        )

    if former_name_rows:
        con.executemany(
            """
            INSERT INTO bronze.sec_submission_former_name
            VALUES (?, ?, ?, ?, ?)
            """,
            former_name_rows,
        )

    print("\nROWS LOADED")

    for table in [
        "sec_submission_entity",
        "sec_submission_ticker",
        "sec_submission_former_name",
    ]:
        n = con.execute(
            f"""
            SELECT COUNT(*)
            FROM bronze.{table}
            """
        ).fetchone()[0]

        print(
            f"{table:30s} {n:,}"
        )

    con.close()


if __name__ == "__main__":
    main()
