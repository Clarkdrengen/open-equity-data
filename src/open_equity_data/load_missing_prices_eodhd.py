import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from open_equity_data.db import connect
from open_equity_data.eodhd import get_eod


PROVIDER = "EODHD"


def stable_hash(*parts) -> str:
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main():
    con = connect()

    ddl = Path(
        "sql/bronze/create_external_price_observation.sql"
    ).read_text()
    con.execute(ddl)

    missing = con.execute("""
        SELECT
            q.lineage_id,
            q.lineage_code,
            q.session_date,
            q.candidate_ticker AS historical_ticker,
            m.latest_ticker
        FROM silver.missing_price_queue q
        JOIN silver.ticker_lineage_master m
          ON q.lineage_id = m.lineage_id
        WHERE q.reconciliation_status = 'unresolved'
          AND q.candidate_ticker IS NOT NULL
        ORDER BY q.lineage_id, q.session_date
    """).fetchall()

    resolved = 0
    fallback_resolved = 0
    unresolved = 0

    for (
        lineage_id,
        lineage_code,
        session_date,
        historical_ticker,
        latest_ticker,
    ) in missing:

        candidates = [
            (historical_ticker, "historical_ticker_lookup")
        ]

        if latest_ticker != historical_ticker:
            candidates.append(
                (latest_ticker, "lineage_latest_ticker_fallback")
            )

        found = False

        for symbol, lookup_method in candidates:
            date_str = session_date.isoformat()
            rows = get_eod(symbol, date_str, date_str)

            retrieved_at = datetime.now(timezone.utc)
            provider_symbol = f"{symbol}.US"

            response_json = json.dumps(
                rows,
                sort_keys=True,
                separators=(",", ":"),
            )

            request_id = stable_hash(
                PROVIDER,
                provider_symbol,
                lineage_id,
                historical_ticker,
                date_str,
                lookup_method,
                response_json,
            )

            con.execute("""
                INSERT OR IGNORE INTO bronze.external_price_request
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                request_id,
                PROVIDER,
                provider_symbol,
                lineage_id,
                lineage_code,
                historical_ticker,
                session_date,
                lookup_method,
                len(rows),
                response_json,
                retrieved_at,
            ])

            exact = [
                row for row in rows
                if row.get("date") == date_str
            ]

            if not exact:
                continue

            row = exact[0]

            raw_payload_json = json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
            )

            observation_id = stable_hash(
                request_id,
                raw_payload_json,
            )

            con.execute("""
                INSERT OR IGNORE INTO bronze.external_price_observation
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                observation_id,
                request_id,
                PROVIDER,
                provider_symbol,
                lineage_id,
                lineage_code,
                historical_ticker,
                session_date,
                lookup_method,
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("adjusted_close"),
                row.get("volume"),
                retrieved_at,
                raw_payload_json,
            ])

            found = True
            resolved += 1

            if lookup_method == "lineage_latest_ticker_fallback":
                fallback_resolved += 1

            break

        if not found:
            unresolved += 1

    print(f"Queue rows:        {len(missing)}")
    print(f"Resolved:          {resolved}")
    print(f"  via fallback:    {fallback_resolved}")
    print(f"Unresolved:        {unresolved}")


if __name__ == "__main__":
    main()
