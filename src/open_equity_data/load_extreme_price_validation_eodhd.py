from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


PROVIDER = "EODHD"
BASE_URL = "https://eodhd.com/api/eod"
WINDOW_PAD_DAYS = 10
MAX_ATTEMPTS = 5
REQUEST_DELAY_SECONDS = 0.15


def stable_hash(*parts: object) -> str:
    value = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def main():
    load_dotenv(".env")

    token = os.environ["EODHD_API_TOKEN"]
    con = connect()

    repo = Path.cwd()
    ddl = repo / "sql/bronze/create_external_price_validation_tables.sql"
    con.execute(ddl.read_text())

    targets = con.execute("""
        SELECT
            ticker,
            MIN(date) AS min_extreme_date,
            MAX(date) AS max_extreme_date,
            COUNT(*) AS extreme_rows,
            COUNT(DISTINCT security_id) AS securities
        FROM silver.security_daily_return
        WHERE research_eligible
          AND ABS(gross_total_return) > 1.0
        GROUP BY ticker
        ORDER BY ticker
    """).fetchall()

    print(f"Extreme-return tickers: {len(targets)}", flush=True)
    print(
        "Strategy: one EODHD request per ticker, spanning the earliest "
        "to latest extreme event plus +/-10 calendar days.",
        flush=True,
    )
    print("Existing successful/404 requests are reused.", flush=True)

    made = 0
    cached = 0
    not_found = 0
    failed = 0
    empty_200 = 0
    observations_written = 0
    start_all = time.time()

    with httpx.Client(timeout=90.0) as client:
        for idx, (ticker, min_date, max_date, extreme_rows, securities) in enumerate(
            targets, start=1
        ):
            from_date = parse_date(min_date) - timedelta(days=WINDOW_PAD_DAYS)
            to_date = parse_date(max_date) + timedelta(days=WINDOW_PAD_DAYS)
            provider_symbol = f"{ticker}.US"

            request_id = stable_hash(
                PROVIDER,
                provider_symbol,
                from_date.isoformat(),
                to_date.isoformat(),
                "daily_raw_validation_v1",
            )

            cached_row = con.execute("""
                SELECT status_code, response_row_count
                FROM bronze.external_price_validation_request
                WHERE request_id = ?
                  AND status_code IN (200, 404)
            """, [request_id]).fetchone()

            if cached_row is not None:
                cached += 1
                status_code, row_count = cached_row
                if status_code == 404:
                    not_found += 1
                if status_code == 200 and (row_count or 0) == 0:
                    empty_200 += 1
            else:
                response = None
                error_text = None

                for attempt in range(MAX_ATTEMPTS):
                    try:
                        response = client.get(
                            f"{BASE_URL}/{provider_symbol}",
                            params={
                                "api_token": token,
                                "fmt": "json",
                                "period": "d",
                                "order": "a",
                                "from": from_date.isoformat(),
                                "to": to_date.isoformat(),
                            },
                        )
                    except Exception as exc:
                        error_text = repr(exc)
                        response = None

                    if response is not None and response.status_code in (200, 404):
                        break

                    status = None if response is None else response.status_code
                    if status in (429, 500, 502, 503, 504) or response is None:
                        wait = min(2 ** attempt, 16)
                        print(
                            f"  retry {ticker}: status={status}, "
                            f"attempt={attempt + 1}/{MAX_ATTEMPTS}, wait={wait}s",
                            flush=True,
                        )
                        time.sleep(wait)
                        continue

                    break

                retrieved_at = datetime.now(timezone.utc)

                if response is None:
                    status_code = None
                    payload = None
                    row_count = 0
                    failed += 1
                else:
                    status_code = response.status_code

                    if status_code == 200:
                        try:
                            payload = response.json()
                        except Exception as exc:
                            payload = None
                            error_text = f"JSON decode failed: {exc!r}"

                        if not isinstance(payload, list):
                            row_count = 0
                            error_text = (
                                error_text
                                or f"Expected JSON list, got {type(payload).__name__}"
                            )
                        else:
                            row_count = len(payload)

                    else:
                        payload = None
                        row_count = 0
                        error_text = response.text[:2000]

                con.execute("""
                    INSERT OR REPLACE INTO
                    bronze.external_price_validation_request
                    (
                        request_id,
                        provider,
                        ticker,
                        provider_symbol,
                        from_date,
                        to_date,
                        status_code,
                        response_row_count,
                        error_text,
                        retrieved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    request_id,
                    PROVIDER,
                    ticker,
                    provider_symbol,
                    from_date,
                    to_date,
                    status_code,
                    row_count,
                    error_text,
                    retrieved_at,
                ])

                if status_code == 404:
                    not_found += 1

                elif status_code == 200 and isinstance(payload, list):
                    made += 1

                    if len(payload) == 0:
                        empty_200 += 1

                    for row in payload:
                        row_date = row.get("date")
                        if not row_date:
                            continue

                        raw_json = json.dumps(
                            row,
                            sort_keys=True,
                            separators=(",", ":"),
                        )

                        con.execute("""
                            INSERT OR REPLACE INTO
                            bronze.external_price_validation_observation
                            (
                                provider,
                                provider_symbol,
                                ticker,
                                date,
                                open,
                                high,
                                low,
                                close,
                                adjusted_close,
                                volume,
                                request_id,
                                retrieved_at,
                                raw_payload_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, [
                            PROVIDER,
                            provider_symbol,
                            ticker,
                            row_date,
                            row.get("open"),
                            row.get("high"),
                            row.get("low"),
                            row.get("close"),
                            row.get("adjusted_close"),
                            row.get("volume"),
                            request_id,
                            retrieved_at,
                            raw_json,
                        ])
                        observations_written += 1

                else:
                    failed += 1

                time.sleep(REQUEST_DELAY_SECONDS)

            elapsed = time.time() - start_all
            rate = idx / elapsed if elapsed > 0 else 0.0
            eta = (len(targets) - idx) / rate if rate > 0 else 0.0

            if idx == 1 or idx % 25 == 0 or idx == len(targets):
                print(
                    f"[{idx}/{len(targets)} "
                    f"{100 * idx / len(targets):5.1f}%] "
                    f"{ticker}: {extreme_rows} extreme rows | "
                    f"made={made} cached={cached} 404={not_found} failed={failed} | "
                    f"ETA {eta / 60:.1f} min",
                    flush=True,
                )

    print("\nDOWNLOAD SUMMARY", flush=True)
    print(f"Target tickers:          {len(targets)}")
    print(f"API 200 requests made:  {made}")
    print(f"Cache hits:              {cached}")
    print(f"404 symbol not found:    {not_found}")
    print(f"200 but empty:           {empty_200}")
    print(f"Other failures:          {failed}")
    print(f"Observations written:    {observations_written}")


if __name__ == "__main__":
    main()
