"""
Audit EODHD quarterly fundamentals coverage against the actual
primary-exchange research universe.

Purpose
-------
This is a coverage diagnostic only. It does not persist fundamentals
to Bronze yet.

It checks:
- API success
- historical depth
- commonStockSharesOutstanding availability
- filing_date availability
- whether fundamentals cover the start of each security's research history
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

from open_equity_data.db import connect


OUTPUT = Path(
    "artifacts/research/eodhd_fundamentals_coverage.csv"
)

SAMPLE_SIZE = 200


def token() -> str:
    load_dotenv(dotenv_path=".env")

    value = os.environ.get(
        "EODHD_API_TOKEN"
    )

    if not value:
        raise RuntimeError(
            "EODHD_API_TOKEN is not set"
        )

    return value


def build_sample() -> pd.DataFrame:
    """
    Deterministic sample spread across security-history lengths.

    We deliberately include:
    - short histories
    - medium histories
    - long histories
    - securities ending early
    - securities surviving to the end of the sample

    20 names are selected from each of 10 history-length deciles.
    """

    con = connect()

    try:
        frame = con.execute("""
            WITH security_summary AS (
                SELECT
                    security_id,
                    ticker,
                    MIN(date) AS first_date,
                    MAX(date) AS last_date,
                    COUNT(*) AS research_rows
                FROM silver.research_universe_eligibility
                WHERE primary_research_eligible_exchange
                GROUP BY 1, 2
            ),

            ranked AS (
                SELECT
                    *,
                    NTILE(10) OVER (
                        ORDER BY research_rows
                    ) AS history_decile
                FROM security_summary
            ),

            sampled AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY history_decile
                        ORDER BY
                            md5(
                                CAST(security_id AS VARCHAR)
                                || '|'
                                || ticker
                                || '|eodhd-fundamentals-audit-v1'
                            )
                    ) AS sample_rank
                FROM ranked
            )

            SELECT
                security_id,
                ticker,
                first_date,
                last_date,
                research_rows,
                history_decile
            FROM sampled
            WHERE sample_rank <= 20
            ORDER BY
                history_decile,
                sample_rank
        """).df()

    finally:
        con.close()

    return frame


def fetch_quarterly_balance_sheet(
    client: httpx.Client,
    ticker: str,
    api_token: str,
) -> tuple[int, dict]:
    url = (
        "https://eodhd.com/api/v1.1/"
        f"fundamentals/{ticker}.US"
    )

    response = client.get(
        url,
        params={
            "api_token": api_token,
            "filter":
                "Financials::Balance_Sheet::quarterly",
        },
    )

    if response.status_code != 200:
        return response.status_code, {}

    data = response.json()

    if not isinstance(data, dict):
        return response.status_code, {}

    return response.status_code, data


def main() -> None:
    sample = build_sample()

    print(
        f"Audit sample: {len(sample):,} securities",
        flush=True,
    )

    api_token = token()

    results = []

    started = time.time()

    with httpx.Client(
        timeout=60.0,
        follow_redirects=True,
    ) as client:

        for i, row in enumerate(
            sample.itertuples(index=False),
            start=1,
        ):
            try:
                status, data = (
                    fetch_quarterly_balance_sheet(
                        client,
                        row.ticker,
                        api_token,
                    )
                )

                records = [
                    value
                    for value in data.values()
                    if isinstance(value, dict)
                ]

                dates = sorted(
                    r.get("date")
                    for r in records
                    if r.get("date")
                )

                share_records = [
                    r
                    for r in records
                    if r.get(
                        "commonStockSharesOutstanding"
                    )
                    not in (
                        None,
                        "",
                        "0",
                        0,
                    )
                ]

                filed_records = [
                    r
                    for r in records
                    if r.get("filing_date")
                    not in (
                        None,
                        "",
                    )
                ]

                usable_records = [
                    r
                    for r in records
                    if (
                        r.get(
                            "commonStockSharesOutstanding"
                        )
                        not in (
                            None,
                            "",
                            "0",
                            0,
                        )
                        and r.get(
                            "filing_date"
                        )
                        not in (
                            None,
                            "",
                        )
                    )
                ]

                earliest = (
                    dates[0]
                    if dates
                    else None
                )

                latest = (
                    dates[-1]
                    if dates
                    else None
                )

                covers_research_start = bool(
                    earliest
                    and earliest
                    <= str(row.first_date)
                )

                covers_research_end = bool(
                    latest
                    and latest
                    >= str(row.last_date)
                )

                results.append(
                    {
                        "security_id":
                            row.security_id,

                        "ticker":
                            row.ticker,

                        "research_first_date":
                            row.first_date,

                        "research_last_date":
                            row.last_date,

                        "research_rows":
                            row.research_rows,

                        "history_decile":
                            row.history_decile,

                        "http_status":
                            status,

                        "quarterly_records":
                            len(records),

                        "earliest_fundamental_date":
                            earliest,

                        "latest_fundamental_date":
                            latest,

                        "records_with_shares":
                            len(share_records),

                        "records_with_filing_date":
                            len(filed_records),

                        "usable_records":
                            len(usable_records),

                        "covers_research_start":
                            covers_research_start,

                        "covers_research_end":
                            covers_research_end,

                        "error":
                            None,
                    }
                )

            except Exception as exc:
                results.append(
                    {
                        "security_id":
                            row.security_id,
                        "ticker":
                            row.ticker,
                        "research_first_date":
                            row.first_date,
                        "research_last_date":
                            row.last_date,
                        "research_rows":
                            row.research_rows,
                        "history_decile":
                            row.history_decile,
                        "http_status":
                            None,
                        "quarterly_records":
                            0,
                        "earliest_fundamental_date":
                            None,
                        "latest_fundamental_date":
                            None,
                        "records_with_shares":
                            0,
                        "records_with_filing_date":
                            0,
                        "usable_records":
                            0,
                        "covers_research_start":
                            False,
                        "covers_research_end":
                            False,
                        "error":
                            repr(exc),
                    }
                )

            elapsed = (
                time.time()
                - started
            )

            avg = (
                elapsed / i
            )

            remaining = (
                avg
                * (
                    len(sample)
                    - i
                )
            )

            last = results[-1]

            print(
                f"[{i:3d}/{len(sample)}] "
                f"{row.ticker:10s} "
                f"HTTP={str(last['http_status']):>4s} "
                f"records={last['quarterly_records']:3d} "
                f"usable={last['usable_records']:3d} "
                f"start={str(last['covers_research_start']):5s} "
                f"end={str(last['covers_research_end']):5s} "
                f"| elapsed={elapsed:6.1f}s "
                f"ETA={remaining:6.1f}s",
                flush=True,
            )

    result = pd.DataFrame(
        results
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT,
        index=False,
    )

    print("\nCOVERAGE SUMMARY")
    print("----------------")

    print(
        "HTTP 200:",
        f"{(
            result.http_status
            == 200
        ).mean():.1%}",
    )

    print(
        "Any usable PIT shares:",
        f"{(
            result.usable_records
            > 0
        ).mean():.1%}",
    )

    print(
        "Covers research start:",
        f"{result.covers_research_start.mean():.1%}",
    )

    print(
        "Covers research end:",
        f"{result.covers_research_end.mean():.1%}",
    )

    print(
        "Complete filing dates:",
        f"{(
            result.records_with_filing_date
            == result.quarterly_records
        ).mean():.1%}",
    )

    print(
        "\nBY HISTORY DECILE"
    )

    summary = (
        result
        .groupby(
            "history_decile",
            observed=True,
        )
        .agg(
            securities=(
                "security_id",
                "size",
            ),
            http_200=(
                "http_status",
                lambda x:
                    (x == 200).mean(),
            ),
            usable=(
                "usable_records",
                lambda x:
                    (x > 0).mean(),
            ),
            covers_start=(
                "covers_research_start",
                "mean",
            ),
            covers_end=(
                "covers_research_end",
                "mean",
            ),
        )
        .reset_index()
    )

    print(
        summary.to_string(
            index=False,
        )
    )

    print(
        "\nFAILURES / GAPS"
    )

    gaps = result.loc[
        (
            result.http_status != 200
        )
        |
        (
            result.usable_records == 0
        )
        |
        (
            ~result.covers_research_start
        )
    ].sort_values(
        [
            "research_rows",
            "ticker",
        ],
        ascending=[
            False,
            True,
        ],
    )

    if gaps.empty:
        print("None")
    else:
        print(
            gaps[
                [
                    "ticker",
                    "research_first_date",
                    "research_last_date",
                    "research_rows",
                    "http_status",
                    "quarterly_records",
                    "usable_records",
                    "earliest_fundamental_date",
                    "latest_fundamental_date",
                    "covers_research_start",
                ]
            ].to_string(
                index=False,
            )
        )

    print(
        "\nSaved:",
        OUTPUT,
    )


if __name__ == "__main__":
    main()
