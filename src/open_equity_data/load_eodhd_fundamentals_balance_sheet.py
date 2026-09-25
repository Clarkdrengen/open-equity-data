"""
Concurrent EODHD quarterly balance-sheet fundamentals loader.

Primary field:
    commonStockSharesOutstanding

Point-in-time availability:
    filing_date

Architecture
------------
- concurrent HTTP/cache workers
- globally rate-limited network requests
- retries with exponential backoff
- one DuckDB writer only
- restartable from Bronze state and local cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


BASE_URL = "https://eodhd.com/api/v1.1/fundamentals"

CACHE_DIR = Path(
    "data/external/eodhd/fundamentals_balance_sheet"
)

DEFAULT_WORKERS = 8
DEFAULT_REQUESTS_PER_SECOND = 10.0
MAX_RETRIES = 4


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
        ORDER BY research_rows DESC, ticker
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

    return list(
        dict.fromkeys(candidates)
    )


def cache_path_for(
    provider_symbol: str,
) -> Path:
    safe = (
        provider_symbol
        .replace("/", "_")
        .replace("\\", "_")
    )

    return (
        CACHE_DIR
        / f"{safe}.json"
    )


def parse_float(
    value,
) -> float | None:
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
                raw.get(
                    "currency_symbol"
                ),
                json.dumps(
                    raw,
                    sort_keys=True,
                ),
                retrieved_at,
            )
        )

    return rows


class AsyncRateLimiter:
    """
    Simple global spacing limiter.

    A rate of 10 means network requests begin at least
    ~0.10 seconds apart globally.
    """

    def __init__(
        self,
        requests_per_second: float,
    ):
        if requests_per_second <= 0:
            raise ValueError(
                "requests_per_second must be positive"
            )

        self.interval = (
            1.0
            / requests_per_second
        )

        self.lock = asyncio.Lock()

        self.next_time = 0.0

    async def acquire(self) -> None:
        async with self.lock:
            loop = (
                asyncio.get_running_loop()
            )

            now = loop.time()

            wait = max(
                0.0,
                self.next_time - now,
            )

            if wait > 0:
                await asyncio.sleep(
                    wait
                )

            now = loop.time()

            self.next_time = (
                max(
                    self.next_time,
                    now,
                )
                + self.interval
            )


@dataclass
class FetchResult:
    ticker: str
    provider_symbol: str
    status: int | None
    rows: list[tuple]
    usable: int
    cache_path: Path
    from_cache: bool
    error: str | None
    attempts: int


async def fetch_http_json(
    client: httpx.AsyncClient,
    limiter: AsyncRateLimiter,
    token: str,
    provider_symbol: str,
) -> tuple[int | None, dict, str | None, int]:

    url = (
        f"{BASE_URL}/"
        f"{provider_symbol}"
    )

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            await limiter.acquire()

            response = await client.get(
                url,
                params={
                    "api_token": token,
                    "filter":
                        "Financials::Balance_Sheet::quarterly",
                },
            )

            status = (
                response.status_code
            )

            if status == 200:
                payload = response.json()

                if not isinstance(
                    payload,
                    dict,
                ):
                    payload = {}

                return (
                    status,
                    payload,
                    None,
                    attempt,
                )

            # Retry provider throttling / temporary server errors.
            if (
                status == 429
                or 500 <= status <= 599
            ):
                last_error = (
                    f"HTTP {status}"
                )

                await asyncio.sleep(
                    min(
                        2 ** attempt,
                        15,
                    )
                )

                continue

            # Ordinary 4xx responses are not retryable.
            return (
                status,
                {},
                None,
                attempt,
            )

        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:

            last_error = repr(
                exc
            )

            await asyncio.sleep(
                min(
                    2 ** attempt,
                    15,
                )
            )

    return (
        None,
        {},
        last_error,
        MAX_RETRIES,
    )


async def fetch_provider_symbol(
    client: httpx.AsyncClient,
    limiter: AsyncRateLimiter,
    token: str,
    ticker: str,
    provider_symbol: str,
    refresh: bool,
) -> FetchResult:

    path = cache_path_for(
        provider_symbol
    )

    retrieved_at = (
        utc_now_naive()
    )

    if (
        path.exists()
        and not refresh
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

            usable = sum(
                row[3] is not None
                and row[4] is not None
                for row in rows
            )

            return FetchResult(
                ticker=ticker,
                provider_symbol=
                    provider_symbol,
                status=200,
                rows=rows,
                usable=usable,
                cache_path=path,
                from_cache=True,
                error=None,
                attempts=0,
            )

        except (
            json.JSONDecodeError,
            OSError,
        ):
            pass

    (
        status,
        payload,
        error,
        attempts,
    ) = await fetch_http_json(
        client,
        limiter,
        token,
        provider_symbol,
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

    if status == 200:
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

    return FetchResult(
        ticker=ticker,
        provider_symbol=
            provider_symbol,
        status=status,
        rows=rows,
        usable=usable,
        cache_path=path,
        from_cache=False,
        error=error,
        attempts=attempts,
    )


async def fetch_ticker(
    client: httpx.AsyncClient,
    limiter: AsyncRateLimiter,
    token: str,
    ticker: str,
    refresh: bool,
) -> FetchResult:

    results = []

    for provider_symbol in (
        provider_candidates(
            ticker
        )
    ):
        result = (
            await fetch_provider_symbol(
                client=client,
                limiter=limiter,
                token=token,
                ticker=ticker,
                provider_symbol=
                    provider_symbol,
                refresh=refresh,
            )
        )

        results.append(
            result
        )

        if (
            result.status == 200
            and result.usable > 0
        ):
            return result

    # Return the best available attempt.
    return max(
        results,
        key=lambda r: (
            r.status == 200,
            r.usable,
            len(r.rows),
        ),
    )


def replace_ticker_rows(
    con,
    result: FetchResult,
) -> None:

    ticker = result.ticker

    retrieved_at = (
        result.rows[0][7]
        if result.rows
        else utc_now_naive()
    )

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

    if result.rows:
        con.executemany("""
            INSERT INTO
            bronze.eodhd_fundamental_balance_sheet_observation
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, result.rows)

    period_dates = sorted(
        row[2]
        for row in result.rows
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
        result.ticker,
        result.provider_symbol,
        (
            result.status
            if result.status is not None
            else -1
        ),
        len(result.rows),
        result.usable,
        earliest,
        latest,
        retrieved_at,
        str(
            result.cache_path
        ),
        result.error,
    ])


async def worker(
    worker_id: int,
    input_queue: asyncio.Queue,
    output_queue: asyncio.Queue,
    client: httpx.AsyncClient,
    limiter: AsyncRateLimiter,
    token: str,
    refresh: bool,
) -> None:

    while True:
        item = await input_queue.get()

        if item is None:
            input_queue.task_done()
            return

        ticker = item[0]

        try:
            result = await fetch_ticker(
                client=client,
                limiter=limiter,
                token=token,
                ticker=ticker,
                refresh=refresh,
            )

        except Exception as exc:
            result = FetchResult(
                ticker=ticker,
                provider_symbol=
                    provider_candidates(
                        ticker
                    )[0],
                status=None,
                rows=[],
                usable=0,
                cache_path=
                    cache_path_for(
                        provider_candidates(
                            ticker
                        )[0]
                    ),
                from_cache=False,
                error=repr(exc),
                attempts=0,
            )

        await output_queue.put(
            result
        )

        input_queue.task_done()


async def run_async(
    con,
    pending: list[tuple],
    token: str,
    workers: int,
    requests_per_second: float,
    refresh: bool,
) -> None:

    input_queue = asyncio.Queue()
    output_queue = asyncio.Queue()

    for item in pending:
        await input_queue.put(
            item
        )

    for _ in range(workers):
        await input_queue.put(
            None
        )

    limiter = AsyncRateLimiter(
        requests_per_second
    )

    limits = httpx.Limits(
        max_connections=max(
            workers * 2,
            16,
        ),
        max_keepalive_connections=max(
            workers,
            8,
        ),
    )

    timeout = httpx.Timeout(
        60.0,
        connect=20.0,
    )

    started = time.time()

    successes = 0
    no_usable = 0
    errors = 0
    cache_hits = 0
    retries = 0

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        limits=limits,
    ) as client:

        tasks = [
            asyncio.create_task(
                worker(
                    worker_id=i,
                    input_queue=
                        input_queue,
                    output_queue=
                        output_queue,
                    client=client,
                    limiter=limiter,
                    token=token,
                    refresh=refresh,
                )
            )
            for i in range(
                workers
            )
        ]

        total = len(
            pending
        )

        for i in range(
            1,
            total + 1,
        ):
            result = (
                await output_queue.get()
            )

            # Single-writer section.
            replace_ticker_rows(
                con,
                result,
            )

            if result.from_cache:
                cache_hits += 1

            if result.attempts > 1:
                retries += (
                    result.attempts
                    - 1
                )

            if (
                result.status == 200
                and result.usable > 0
            ):
                successes += 1

            elif result.status == 200:
                no_usable += 1

            else:
                errors += 1

            elapsed = (
                time.time()
                - started
            )

            throughput = (
                i / elapsed
                if elapsed > 0
                else 0.0
            )

            remaining = (
                (total - i)
                / throughput
                if throughput > 0
                else 0.0
            )

            print(
                f"[{i:5d}/{total:5d}] "
                f"{result.ticker:10s} "
                f"HTTP={str(result.status):>4s} "
                f"records={len(result.rows):3d} "
                f"usable={result.usable:3d} "
                f"| ok={successes:,} "
                f"empty={no_usable:,} "
                f"err={errors:,} "
                f"cache={cache_hits:,} "
                f"retry={retries:,} "
                f"| {throughput:5.1f}/s "
                f"elapsed={elapsed:7.1f}s "
                f"ETA={remaining:7.1f}s",
                flush=True,
            )

            output_queue.task_done()

        await input_queue.join()

        await asyncio.gather(
            *tasks
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
    )

    parser.add_argument(
        "--retry-success",
        action="store_true",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
    )

    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=
            DEFAULT_REQUESTS_PER_SECOND,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.workers < 1:
        raise SystemExit(
            "--workers must be >= 1"
        )

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
        else already_successful(
            con
        )
    )

    pending = [
        row
        for row in targets
        if row[0]
        not in successful
    ]

    if args.limit is not None:
        pending = pending[
            :args.limit
        ]

    print(
        f"Universe tickers: "
        f"{len(targets):,}",
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

    print(
        f"Workers: {args.workers}",
        flush=True,
    )

    print(
        f"Network throttle: "
        f"{args.requests_per_second:.1f} req/s",
        flush=True,
    )

    if not pending:
        con.close()
        return

    asyncio.run(
        run_async(
            con=con,
            pending=pending,
            token=api_token(),
            workers=args.workers,
            requests_per_second=
                args.requests_per_second,
            refresh=args.refresh,
        )
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
            FROM
            bronze.eodhd_fundamental_balance_sheet_request
        """).fetchone()
    )

    print(
        con.execute("""
            SELECT
                COUNT(*) AS observations,
                COUNT(*) FILTER (
                    WHERE
                        filing_date IS NOT NULL
                    AND
                        common_stock_shares_outstanding
                        IS NOT NULL
                ) AS usable_observations
            FROM
            bronze.eodhd_fundamental_balance_sheet_observation
        """).fetchone()
    )

    con.close()


if __name__ == "__main__":
    main()
