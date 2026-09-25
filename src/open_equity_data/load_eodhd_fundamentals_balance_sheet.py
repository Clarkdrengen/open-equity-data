"""
Load EODHD quarterly balance-sheet fundamentals for the strict
primary-exchange common-stock research universe.

Primary research field:
    commonStockSharesOutstanding

Point-in-time availability field:
    filing_date

Design
------
- raw responses are cached locally
- DuckDB Bronze tables are restartable
- successful tickers are skipped on rerun unless --refresh is supplied
- every ticker prints progress, elapsed time, and ETA
- raw quarterly rows are retained for provenance
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


BASE_URL = "https://eodhd.com/api/v1.1/fundamentals"

CACHE_DIR = Path(
    "data/external/eodhd/fundamentals_balance_sheet"
)


def api_token() -> str:
    load_dotenv(dotenv_path=".env")

    value = os.environ.get("EODHD_API_TOKEN")

    if not value:
        raise RuntimeError(
            "EODHD_API_TOKEN is not set"
        )

    return value


def utc_now_naive() -> datetime:
    return datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )


def initialise_tables(con) -> None:
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS bronze
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS
        bronze.eodhd_fundamental_balance_sheet_request
        (
            ticker VARCHAR,
            provider_symbol VARCHAR,
            http_status INTEGER,
            record_count INTEGER,
            usable_record_count INTEGER,
            earliest_period_date DATE,
            latest_period_date DATE,
            retrieved_at TIMESTAMP,
            cache_path VARCHAR,
            error VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS
        bronze.eodhd_fundamental_balance_sheet_observation
        (
            ticker VARCHAR,
            provider_symbol VARCHAR,
            period_date DATE,
            filing_date DATE,
            common_stock_shares_outstanding DOUBLE,
            currency_symbol VARCHAR,
            raw_payload_json VARCHAR,
            retrieved_at TIMESTAMP
        )
    """)


def universe_targets(con) -> list[tuple]:
    return con.execute("""
        SELECT
            ticker,
            COUNT(*) AS research_rows,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM silver.research_universe_eligibility
        WHERE primary_research_eligible_exchange
        GROUP BY ticker
        ORDER BY
            research_rows DESC,
            ticker
    """).fetchall()


def already_successful(con) -> set[str]:
    return {
        row[0]
        for row in con.execute("""
            SELECT DISTINCT ticker
            FROM bronze.eodhd_fundamental_balance_sheet_request
            WHERE http_status = 200
              AND usable_record_count > 0
        """).fetchall()
    }


def provider_candidates(
    ticker: str,
) -> list[str]:
    raw = ticker.upper()

    candidates = [
        f"{raw}.US",
    ]

    if "." in raw:
        candidates.append(
            f"{raw.replace('.', '-')}.US"
        )

    return list(dict.fromkeys(candidates))


def cache_path_for(
    provider_symbol: str,
) -> Path:
    safe = (
        provider_symbol
        .replace("/", "_")
        .replace("\\", "_")
    )

    return CACHE_DIR / f"{safe}.json"


def fetch_one(
    client: httpx.Client,
    token: str,
    provider_symbol: str,
    refresh: bool,
) -> tuple[int, dict, Path, bool]:
    path = cache_path_for(
        provider_symbol
    )

    if path.exists() and not refresh:
        try:
            payload = json.loads(
                path.read_text()
            )

            return (
                200,
                payload,
                path,
                True,
            )
        except json.JSONDecodeError:
            pass

    url = f"{BASE_URL}/{provider_symbol}"

    response = client.get(
        url,
        params={
            "api_token": token,
            "filter":
                "Financials::Balance_Sheet::quarterly",
        },
    )

    status = response.status_code

    if status != 200:
        return (
            status,
            {},
            path,
            False,
        )

    payload = response.json()

    if not isinstance(payload, dict):
        payload = {}

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return (
        status,
        payload,
        path,
        False,
    )


def parse_float(value) -> float | None:
    if value in (
        None,
        "",
        "0",
        0,
    ):
        return None

    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result <= 0:
        return None

    return result


def parse_payload(
    ticker: str,
    provider_symbol: str,
    payload: dict,
    retrieved_at: datetime,
) -> list[tuple]:
    rows = []

    for key, raw in payload.items():
        if not isinstance(
            raw,
            dict,
        ):
            continue

        period_date = (
            raw.get("date")
            or key
        )

        filing_date = raw.get(
            "filing_date"
        )

        shares = parse_float(
            raw.get(
                "commonStockSharesOutstanding"
            )
        )

        rows.append(
            (
                ticker,
                provider_symbol,
                period_date,
                filing_date,
                shares,
                raw.get("currency_symbol"),
                json.dumps(
                    raw,
                    sort_keys=True,
                ),
                retrieved_at,
            )
        )

    return rows


def replace_ticker_rows(
    con,
    *,
    ticker: str,
    provider_symbol: str,
    status: int,
    rows: list[tuple],
    cache_path: Path,
    retrieved_at: datetime,
    error: str | None,
) -> None:
    con.execute("""
        DELETE FROM
        bronze.eodhd_fundamental_balance_sheet_observation
        WHERE ticker = ?
    """, [ticker])

    con.execute("""
        DELETE FROM
        bronze.eodhd_fundamental_balance_sheet_request
        WHERE ticker = ?
    """, [ticker])

    if rows:
        con.executemany("""
            INSERT INTO
            bronze.eodhd_fundamental_balance_sheet_observation
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

    usable = [
        row
        for row in rows
        if (
            row[3] is not None
            and row[4] is not None
        )
    ]

    period_dates = sorted(
        row[2]
        for row in rows
        if row[2] is not None
    )

    earliest = (
        period_dates[0]
        if period_dates
        else None
    )

    latest = (
        period_dates[-1]
        if period_dates
        else None
    )

    con.execute("""
        INSERT INTO
        bronze.eodhd_fundamental_balance_sheet_request
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ticker,
        provider_symbol,
        status,
        len(rows),
        len(usable),
        earliest,
        latest,
        retrieved_at,
        str(cache_path),
        error,
    ])


def load_ticker(
    con,
    client: httpx.Client,
    token: str,
    ticker: str,
    refresh: bool,
) -> dict:
    retrieved_at = utc_now_naive()

    attempts = []
    last_error = None

    for provider_symbol in provider_candidates(
        ticker
    ):
        try:
            (
                status,
                payload,
                path,
                from_cache,
            ) = fetch_one(
                client,
                token,
                provider_symbol,
                refresh,
            )

            rows = (
                parse_payload(
                    ticker,
                    provider_symbol,
                    payload,
                    retrieved_at,
                )
                if status == 200
                else []
            )

            usable = sum(
                row[3] is not None
                and row[4] is not None
                for row in rows
            )

            attempts.append(
                (
                    provider_symbol,
                    status,
                    len(rows),
                    usable,
                    path,
                    from_cache,
                )
            )

            if status == 200 and usable > 0:
                replace_ticker_rows(
                    con,
                    ticker=ticker,
                    provider_symbol=provider_symbol,
                    status=status,
                    rows=rows,
                    cache_path=path,
                    retrieved_at=retrieved_at,
                    error=None,
                )

                return {
                    "ticker": ticker,
                    "provider_symbol": provider_symbol,
                    "status": status,
                    "records": len(rows),
                    "usable": usable,
                    "from_cache": from_cache,
                    "error": None,
                }

        except Exception as exc:
            last_error = repr(exc)

            attempts.append(
                (
                    provider_symbol,
                    None,
                    0,
                    0,
                    cache_path_for(
                        provider_symbol
                    ),
                    False,
                )
            )

    if attempts:
        best = max(
            attempts,
            key=lambda x: (
                x[1] == 200,
                x[3],
                x[2],
            ),
        )

        (
            provider_symbol,
            status,
            record_count,
            usable,
            path,
            from_cache,
        ) = best

        rows = []

        if (
            status == 200
            and path.exists()
        ):
            try:
                payload = json.loads(
                    path.read_text()
                )

                rows = parse_payload(
                    ticker,
                    provider_symbol,
                    payload,
                    retrieved_at,
                )
            except Exception:
                rows = []

        replace_ticker_rows(
            con,
            ticker=ticker,
            provider_symbol=provider_symbol,
            status=(
                status
                if status is not None
                else -1
            ),
            rows=rows,
            cache_path=path,
            retrieved_at=retrieved_at,
            error=last_error,
        )

        return {
            "ticker": ticker,
            "provider_symbol": provider_symbol,
            "status": status,
            "records": record_count,
            "usable": usable,
            "from_cache": from_cache,
            "error": last_error,
        }

    raise RuntimeError(
        f"No provider candidates for {ticker}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process only the first N target tickers. "
            "Useful for pilot runs."
        ),
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
    )

    parser.add_argument(
        "--retry-success",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    con = connect()

    initialise_tables(
        con
    )

    targets = universe_targets(
        con
    )

    successful = (
        set()
        if args.retry_success
        else already_successful(con)
    )

    pending = [
        row
        for row in targets
        if row[0] not in successful
    ]

    if args.limit is not None:
        pending = pending[
            :args.limit
        ]

    print(
        f"Universe tickers: {len(targets):,}",
        flush=True,
    )

    print(
        f"Already successful: "
        f"{len(successful):,}",
        flush=True,
    )

    print(
        f"Pending this run: "
        f"{len(pending):,}",
        flush=True,
    )

    if not pending:
        con.close()
        return

    token = api_token()

    started = time.time()

    successes = 0
    no_usable = 0
    errors = 0

    with httpx.Client(
        timeout=60.0,
        follow_redirects=True,
    ) as client:

        for i, (
            ticker,
            research_rows,
            first_date,
            last_date,
        ) in enumerate(
            pending,
            start=1,
        ):
            result = load_ticker(
                con=con,
                client=client,
                token=token,
                ticker=ticker,
                refresh=args.refresh,
            )

            if (
                result["status"] == 200
                and result["usable"] > 0
            ):
                successes += 1

            elif result["status"] == 200:
                no_usable += 1

            else:
                errors += 1

            elapsed = (
                time.time()
                - started
            )

            average = elapsed / i

            remaining = (
                average
                * (
                    len(pending)
                    - i
                )
            )

            cache_flag = (
                " cache"
                if result["from_cache"]
                else ""
            )

            print(
                f"[{i:5d}/{len(pending):5d}] "
                f"{ticker:10s} "
                f"HTTP={str(result['status']):>4s} "
                f"records={result['records']:3d} "
                f"usable={result['usable']:3d}"
                f"{cache_flag} "
                f"| ok={successes:,} "
                f"empty={no_usable:,} "
                f"err={errors:,} "
                f"| elapsed={elapsed:7.1f}s "
                f"ETA={remaining:7.1f}s",
                flush=True,
            )

    print("\nLOAD SUMMARY")
    print("------------")

    print(
        "Successful:",
        successes,
    )

    print(
        "HTTP 200 but no usable PIT shares:",
        no_usable,
    )

    print(
        "HTTP/error failures:",
        errors,
    )

    print("\nBRONZE COUNTS")

    print(
        con.execute("""
            SELECT
                COUNT(*) AS requests,
                COUNT(*) FILTER (
                    WHERE http_status = 200
                ) AS http_200,
                COUNT(*) FILTER (
                    WHERE usable_record_count > 0
                ) AS usable_tickers
            FROM bronze.eodhd_fundamental_balance_sheet_request
        """).fetchone()
    )

    print(
        con.execute("""
            SELECT
                COUNT(*) AS observations,
                COUNT(*) FILTER (
                    WHERE
                        filing_date IS NOT NULL
                    AND common_stock_shares_outstanding
                        IS NOT NULL
                ) AS usable_observations
            FROM bronze.eodhd_fundamental_balance_sheet_observation
        """).fetchone()
    )

    con.close()


if __name__ == "__main__":
    main()
