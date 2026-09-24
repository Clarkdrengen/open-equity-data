from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect

PROVIDER = "EODHD"
BASE_URL = "https://eodhd.com/api/splits"
MAX_ATTEMPTS = 5
REQUEST_DELAY_SECONDS = 0.15


def stable_hash(*parts: object) -> str:
    value = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_split_ratio(value):
    if value is None:
        return None
    txt = str(value).strip()

    # EODHD commonly returns factors like "2.000000/1.000000".
    if "/" in txt:
        left, right = txt.split("/", 1)
        try:
            left = float(left)
            right = float(right)
            if right == 0:
                return None
            return left / right
        except Exception:
            return None

    try:
        return float(txt)
    except Exception:
        return None


def main():
    load_dotenv(".env")
    token = os.environ["EODHD_API_TOKEN"]

    con = connect()
    targets = con.execute("""
        SELECT
            ticker,
            COUNT(*) AS candidate_rows,
            COUNT(DISTINCT security_id) AS securities
        FROM silver.extreme_return_diagnostic
        WHERE diagnostic_class = 'corporate_action_candidate'
        GROUP BY ticker
        ORDER BY ticker
    """).fetchall()

    print(f"Corporate-action candidate tickers: {len(targets)}", flush=True)
    print("Fetching full EODHD split history per ticker.", flush=True)

    made = cached = not_found = failed = empty_200 = observations = 0
    start_all = time.time()

    with httpx.Client(timeout=90.0) as client:
        for idx, (ticker, candidate_rows, securities) in enumerate(targets, start=1):
            provider_symbol = f"{ticker}.US"
            request_id = stable_hash(
                PROVIDER,
                provider_symbol,
                "full_split_history_candidate_validation_v1",
            )

            cached_row = con.execute("""
                SELECT status_code, response_row_count
                FROM bronze.external_split_candidate_validation_request
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
                            },
                        )
                    except Exception as exc:
                        response = None
                        error_text = repr(exc)

                    if response is not None and response.status_code in (200, 404):
                        break

                    status = None if response is None else response.status_code
                    if status in (429, 500, 502, 503, 504) or response is None:
                        wait = min(2 ** attempt, 16)
                        print(
                            f"  retry {ticker}: status={status}, "
                            f"attempt={attempt+1}/{MAX_ATTEMPTS}, wait={wait}s",
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

                        if isinstance(payload, list):
                            row_count = len(payload)
                        else:
                            row_count = 0
                            error_text = (
                                error_text
                                or f"Expected list, got {type(payload).__name__}"
                            )
                    else:
                        payload = None
                        row_count = 0
                        error_text = response.text[:2000]

                con.execute("""
                    INSERT OR REPLACE INTO
                    bronze.external_split_candidate_validation_request
                    (
                        request_id, provider, ticker, provider_symbol,
                        status_code, response_row_count, error_text, retrieved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    request_id, PROVIDER, ticker, provider_symbol,
                    status_code, row_count, error_text, retrieved_at
                ])

                if status_code == 404:
                    not_found += 1

                elif status_code == 200 and isinstance(payload, list):
                    made += 1
                    if len(payload) == 0:
                        empty_200 += 1

                    for row in payload:
                        ex_date = row.get("date")
                        split_factor = (
                            row.get("split")
                            or row.get("splitFactor")
                            or row.get("split_factor")
                        )
                        if not ex_date:
                            continue

                        ratio = parse_split_ratio(split_factor)
                        raw_json = json.dumps(
                            row,
                            sort_keys=True,
                            separators=(",", ":"),
                        )

                        con.execute("""
                            INSERT OR REPLACE INTO
                            bronze.external_split_candidate_validation_observation
                            (
                                provider, provider_symbol, ticker, ex_date,
                                split_factor_text, split_ratio,
                                request_id, retrieved_at, raw_payload_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, [
                            PROVIDER, provider_symbol, ticker, ex_date,
                            None if split_factor is None else str(split_factor),
                            ratio, request_id, retrieved_at, raw_json
                        ])
                        observations += 1
                else:
                    failed += 1

                time.sleep(REQUEST_DELAY_SECONDS)

            elapsed = time.time() - start_all
            rate = idx / elapsed if elapsed > 0 else 0.0
            eta = (len(targets) - idx) / rate if rate > 0 else 0.0

            if idx == 1 or idx % 25 == 0 or idx == len(targets):
                print(
                    f"[{idx}/{len(targets)} "
                    f"{100*idx/len(targets):5.1f}%] {ticker}: "
                    f"candidate_rows={candidate_rows} | "
                    f"made={made} cached={cached} 404={not_found} "
                    f"failed={failed} | ETA {eta/60:.1f} min",
                    flush=True,
                )

    print("\\nDOWNLOAD SUMMARY")
    print(f"Target tickers:          {len(targets)}")
    print(f"API 200 requests made:  {made}")
    print(f"Cache hits:              {cached}")
    print(f"404 symbol not found:    {not_found}")
    print(f"200 but empty:           {empty_200}")
    print(f"Other failures:          {failed}")
    print(f"Split observations:      {observations}")


if __name__ == "__main__":
    main()
