import json
from pathlib import Path

from open_equity_data.db import connect


SOURCE_PATH = Path(
    "data/external/quant_lodge/ticker_changes.json"
)


def load_quant_lodge():
    data = json.loads(SOURCE_PATH.read_text())

    rows = []

    for ticker, values in data.items():
        if not isinstance(values, dict):
            values = {}

        rows.append(
            (
                ticker,
                values.get("cik"),
                values.get("old_ticker"),
                bool(values.get("flat_file_only", False)),
            )
        )

    con = connect()

    con.execute("""
        CREATE OR REPLACE TABLE bronze.ticker_changes_external (
            ticker VARCHAR,
            cik VARCHAR,
            old_ticker VARCHAR,
            flat_file_only BOOLEAN
        )
    """)

    con.executemany(
        """
        INSERT INTO bronze.ticker_changes_external
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )

    print(
        "Loaded",
        con.execute("""
            SELECT COUNT(*)
            FROM bronze.ticker_changes_external
        """).fetchone()[0],
        "ticker-reference rows",
    )

    print("\nFB / META references:")
    for row in con.execute("""
        SELECT *
        FROM bronze.ticker_changes_external
        WHERE ticker IN ('FB', 'META')
           OR old_ticker IN ('FB', 'META')
        ORDER BY ticker
    """).fetchall():
        print(row)

    con.close()


if __name__ == "__main__":
    load_quant_lodge()
