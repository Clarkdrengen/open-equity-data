import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


PROVIDER = "EODHD"
BASE_URL = "https://eodhd.com/api/splits"
WINDOW_BUFFER_DAYS = 45

# HTTP results which are safe to treat as terminal/cacheable.
CACHEABLE_STATUS_CODES = (200, 404)


def stable_hash(*parts) -> str:
    value = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_split(value: str):
    numerator, denominator = value.split("/")

    to_factor = float(numerator)
    for_factor = float(denominator)

    if for_factor == 0:
        raise ValueError(f"Invalid split ratio: {value}")

    return to_factor, for_factor, to_factor / for_factor


def main():
    load_dotenv(".env")

    token = os.environ.get("EODHD_API_TOKEN")
    if not token:
        raise RuntimeError("EODHD_API_TOKEN is not set")

    con = connect()

    con.execute(
        Path(
            "sql/bronze/create_external_split_tables.sql"
        ).read_text()
    )

    # One extraction window per ticker rather than one request per
    # suspicious split event.
    work = con.execute("""
        SELECT
            ticker,
            MIN(source_ex_date) AS min_date,
            MAX(source_ex_date) AS max_date,
            COUNT(*) AS n_candidates
        FROM silver.security_split_candidate
        WHERE validation_status = 'requires_reconciliation'
        GROUP BY ticker
        ORDER BY ticker
    """).fetchall()

    print(f"Tickers requiring reconciliation: {len(work)}")

    queried = 0
    cached = 0
    cached_not_found = 0
    failed = 0
    observations_processed = 0

    with httpx.Client(timeout=30.0) as client:

        for i, (ticker, min_date, max_date, n_candidates) in enumerate(
            work,
            start=1,
        ):
            provider_symbol = f"{ticker}.US"

            start_date = min_date - timedelta(days=WINDOW_BUFFER_DAYS)
            end_date = max_date + timedelta(days=WINDOW_BUFFER_DAYS)

            # Coverage-aware cache.
            #
            # A previous 200 response can be reused if it covers the whole
            # currently required window.
            #
            # A 404 "Symbol not found" is also treated as terminal because
            # rerunning the same provider-symbol lookup is not useful.
            cached_request = con.execute("""
                SELECT
                    request_id,
                    status_code,
                    response_json,
                    retrieved_at
                FROM bronze.external_split_request
                WHERE provider = ?
                  AND provider_symbol = ?
                  AND status_code IN (200, 404)
                  AND start_date <= ?
                  AND end_date >= ?
                ORDER BY
                    (end_date - start_date) ASC,
                    retrieved_at DESC
                LIMIT 1
            """, [
                PROVIDER,
                provider_symbol,
                start_date,
                end_date,
            ]).fetchone()

            if cached_request:
                (
                    request_id,
                    cached_status,
                    response_json,
                    retrieved_at,
                ) = cached_request

                cached += 1

                if cached_status == 404:
                    cached_not_found += 1
                    print(
                        f"[{i}/{len(work)}] "
                        f"{provider_symbol}: "
                        f"{n_candidates} candidate(s), "
                        "cached symbol-not-found"
                    )
                    continue

                payload = json.loads(response_json)

            else:
                response = None

                for attempt in range(5):
                    response = client.get(
                        f"{BASE_URL}/{provider_symbol}",
                        params={
                            "from": start_date.isoformat(),
                            "to": end_date.isoformat(),
                            "api_token": token,
                            "fmt": "json",
                        },
                    )

                    # Successful response.
                    if response.status_code == 200:
                        break

                    # A missing provider symbol is permanent for this lookup.
                    if response.status_code == 404:
                        break

                    # Retry transient provider/server errors.
                    if response.status_code in (
                        429,
                        500,
                        502,
                        503,
                        504,
                    ):
                        wait_seconds = 2 ** attempt

                        print(
                            f"{provider_symbol}: "
                            f"HTTP {response.status_code}; "
                            f"retrying in {wait_seconds}s"
                        )

                        time.sleep(wait_seconds)
                        continue

                    # Do not retry other terminal HTTP responses.
                    break

                retrieved_at = datetime.now(timezone.utc)

                try:
                    payload = response.json()
                except Exception:
                    payload = {"raw_text": response.text}

                response_json = json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                request_id = stable_hash(
                    PROVIDER,
                    provider_symbol,
                    start_date,
                    end_date,
                    response.status_code,
                    response_json,
                )

                con.execute("""
                    INSERT OR IGNORE INTO bronze.external_split_request
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    request_id,
                    PROVIDER,
                    provider_symbol,
                    start_date,
                    end_date,
                    response.status_code,
                    response_json,
                    retrieved_at,
                ])

                if response.status_code == 404:
                    cached_not_found += 1

                    print(
                        f"[{i}/{len(work)}] "
                        f"{provider_symbol}: "
                        f"{n_candidates} candidate(s), "
                        "symbol not found"
                    )
                    continue

                if response.status_code != 200:
                    failed += 1

                    print(
                        f"[{i}/{len(work)}] "
                        f"{provider_symbol}: "
                        f"FAILED HTTP {response.status_code}"
                    )
                    continue

                queried += 1

            # Normalize returned provider observations into Bronze.
            if not isinstance(payload, list):
                print(
                    f"[{i}/{len(work)}] "
                    f"{provider_symbol}: unexpected payload type"
                )
                continue

            for row in payload:
                split_text = row.get("split")
                split_date = row.get("date")

                if not split_text or not split_date:
                    continue

                try:
                    (
                        to_factor,
                        for_factor,
                        split_ratio,
                    ) = parse_split(split_text)

                except Exception as exc:
                    print(
                        f"{provider_symbol} {split_date}: "
                        f"could not parse {split_text!r}: {exc}"
                    )
                    continue

                raw_payload_json = json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                observation_id = stable_hash(
                    PROVIDER,
                    provider_symbol,
                    split_date,
                    split_text,
                )

                con.execute("""
                    INSERT OR IGNORE INTO
                        bronze.external_split_observation
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    observation_id,
                    request_id,
                    PROVIDER,
                    provider_symbol,
                    split_date,
                    to_factor,
                    for_factor,
                    split_ratio,
                    split_text,
                    retrieved_at,
                    raw_payload_json,
                ])

                observations_processed += 1

            print(
                f"[{i}/{len(work)}] "
                f"{provider_symbol}: "
                f"{n_candidates} candidate(s), "
                f"{len(payload)} EODHD event(s)"
            )

    print("\nSUMMARY")
    print(f"Tickers:                  {len(work)}")
    print(f"API requests made:        {queried}")
    print(f"Cache hits:               {cached}")
    print(f"Cached/not-found symbols: {cached_not_found}")
    print(f"Failed requests:          {failed}")
    print(f"Events processed:         {observations_processed}")


if __name__ == "__main__":
    main()
