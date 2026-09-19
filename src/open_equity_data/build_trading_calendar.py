from collections import Counter

import exchange_calendars as xcals

from open_equity_data.db import connect


def main():
    con = connect()

    first_date, last_date = con.execute("""
        SELECT MIN(date), MAX(date)
        FROM bronze.ohlcv
    """).fetchone()

    cal = xcals.get_calendar("XNYS")

    sessions = cal.sessions_in_range(
        first_date.isoformat(),
        last_date.isoformat(),
    )

    raw_rows = []

    for session in sessions:
        market_open = cal.session_open(session)
        market_close = cal.session_close(session)

        session_minutes = int(
            (market_close - market_open).total_seconds() / 60
        )

        raw_rows.append(
            (
                session.date(),
                market_open.to_pydatetime(),
                market_close.to_pydatetime(),
                session_minutes,
            )
        )

    normal_session_minutes = Counter(
        row[3] for row in raw_rows
    ).most_common(1)[0][0]

    rows = [
        (
            session_date,
            market_open,
            market_close,
            session_minutes,
            session_minutes < normal_session_minutes,
            "XNYS",
            "exchange_calendars",
        )
        for (
            session_date,
            market_open,
            market_close,
            session_minutes,
        ) in raw_rows
    ]

    con.execute("""
        CREATE OR REPLACE TABLE silver.trading_calendar (
            session_date DATE PRIMARY KEY,
            market_open TIMESTAMPTZ,
            market_close TIMESTAMPTZ,
            session_minutes INTEGER,
            is_early_close BOOLEAN,
            calendar_code VARCHAR,
            source VARCHAR
        )
    """)

    con.executemany("""
        INSERT INTO silver.trading_calendar
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)

    print(
        con.execute("""
            SELECT
                COUNT(*) AS sessions,
                MIN(session_date) AS first_session,
                MAX(session_date) AS last_session,
                SUM(is_early_close::INT) AS early_closes,
                MAX(session_minutes) AS normal_minutes,
                MIN(session_minutes) AS shortest_minutes
            FROM silver.trading_calendar
        """).fetchall()
    )

    con.close()


if __name__ == "__main__":
    main()
