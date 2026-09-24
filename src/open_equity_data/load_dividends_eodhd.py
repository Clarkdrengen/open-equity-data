import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


PROVIDER = "EODHD"
BASE_URL = "https://eodhd.com/api/div"
CACHEABLE_STATUS_CODES = (200, 404)


def stable_hash(*parts) -> str:
    value = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main():
    load_dotenv(".env")

    token = os.environ["EODHD_API_TOKEN"]
    con = connect()

    con.execute(
        Path("sql/bronze/create_external_dividend_tables.sql").read_text()
    )

    tickers = [
        row[0]
        for row in con.execute("""
            SELECT DISTINCT ticker
            FROM silver.security_dividend_event
            WHERE dividend_resolution_method =
                  'unresolved_same_day_split_basis'
            ORDER BY ticker
        """).fetchall()
    ]

    print(f"Tickers to query: {len(tickers)}")

    queried = 0
    cached = 0
    not_found = 0
    failed = 0
    observations = 0

    with httpx.Client(timeout=60.0) as client:
        for i, ticker in enumerate(tickers, start=1):
            provider_symbol = f"{ticker}.US"

            cached_request = con.execute("""
                SELECT
                    request_id,
                    status_code,
                    response_json,
                    retrieved_at
                FROM bronze.external_dividend_request
                WHERE provider = ?
                  AND provider_symbol = ?
                  AND status_code IN (200, 404)
                ORDER BY retrieved_at DESC
                LIMIT 1
            """, [PROVIDER, provider_symbol]).fetchone()

            if cached_request:
                request_id, status_code, response_json, retrieved_at = cached_request
                cached += 1

                if status_code == 404:
                    not_found += 1
                    print(f"[{i}/{len(tickers)}] {provider_symbol}: cached not found")
                    continue

                payload = json.loads(response_json)

            else:
                response = None

                for attempt in range(5):
                    response = client.get(
                        f"{BASE_URL}/{provider_symbol}",
                        params={
                            "api_token": token,
                            "fmt": "json",
                        },
                    )

                    if response.status_code in CACHEABLE_STATUS_CODES:
                        break

                    if response.status_code in (429, 500, 502, 503, 504):
                        wait = 2 ** attempt
                        print(
                            f"{provider_symbol}: HTTP {response.status_code}; "
                            f"retrying in {wait}s"
                        )
                        time.sleep(wait)
                        continue

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
                    response.status_code,
                    response_json,
                )

                con.execute("""
                    INSERT OR IGNORE INTO bronze.external_dividend_request
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [
                    request_id,
                    PROVIDER,
                    provider_symbol,
                    response.status_code,
                    response_json,
                    retrieved_at,
                ])

                if response.status_code == 404:
                    not_found += 1
                    print(f"[{i}/{len(tickers)}] {provider_symbol}: not found")
                    continue

                if response.status_code != 200:
                    failed += 1
                    print(
                        f"[{i}/{len(tickers)}] {provider_symbol}: "
                        f"FAILED HTTP {response.status_code}"
                    )
                    continue

                queried += 1

            if not isinstance(payload, list):
                continue

            for row in payload:
                ex_date = row.get("date")
                value = row.get("value")

                raw_payload_json = json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                observation_id = stable_hash(
                    PROVIDER,
                    provider_symbol,
                    ex_date,
                    value,
                    row.get("unadjustedValue"),
                )

                con.execute("""
                    INSERT OR IGNORE INTO bronze.external_dividend_observation
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    observation_id,
                    request_id,
                    PROVIDER,
                    provider_symbol,
                    ex_date,
                    row.get("declarationDate"),
                    row.get("recordDate"),
                    row.get("paymentDate"),
                    value,
                    row.get("unadjustedValue"),
                    row.get("currency"),
                    retrieved_at,
                    raw_payload_json,
                ])

                observations += 1

            print(
                f"[{i}/{len(tickers)}] {provider_symbol}: "
                f"{len(payload)} dividend events"
            )

    print("\nSUMMARY")
    print(f"Tickers:              {len(tickers)}")
    print(f"API requests made:    {queried}")
    print(f"Cache hits:           {cached}")
    print(f"Not found:            {not_found}")
    print(f"Failed:               {failed}")
    print(f"Events processed:     {observations}")


if __name__ == "__main__":
    main()
