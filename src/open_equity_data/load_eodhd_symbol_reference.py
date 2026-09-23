import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from open_equity_data.db import connect


BASE_URL = "https://eodhd.com/api/exchange-symbol-list/US"


def main():
    load_dotenv(".env")

    token = os.environ["EODHD_API_TOKEN"]
    con = connect()

    con.execute(
        Path("sql/bronze/create_eodhd_symbol_reference.sql").read_text()
    )

    retrieved_at = datetime.now(timezone.utc)

    with httpx.Client(timeout=60.0) as client:
        for is_delisted in [False, True]:
            r = client.get(
                BASE_URL,
                params={
                    "api_token": token,
                    "fmt": "json",
                    "delisted": int(is_delisted),
                },
            )
            r.raise_for_status()

            rows = r.json()
            print(
                "delisted=",
                int(is_delisted),
                "rows=",
                len(rows),
            )

            for row in rows:
                code = row.get("Code")
                if not code:
                    continue

                provider_symbol = f"{code}.US"

                con.execute("""
                    INSERT OR REPLACE INTO bronze.eodhd_symbol_reference
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    provider_symbol,
                    code,
                    row.get("Exchange"),
                    row.get("Name"),
                    row.get("Country"),
                    row.get("Currency"),
                    row.get("Type"),
                    row.get("Isin"),
                    is_delisted,
                    retrieved_at,
                    json.dumps(
                        row,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ])


if __name__ == "__main__":
    main()
