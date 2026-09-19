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

    rows = [
        (
            session.date(),
            "XNYS",
            "exchange_calendars",
        )
        for session in sessions
    ]

    con.execute("""
        CREATE OR REPLACE TABLE silver.trading_calendar (
            session_date DATE PRIMARY KEY,
            calendar_code VARCHAR,
            source VARCHAR
        )
    """)

    con.executemany("""
        INSERT INTO silver.trading_calendar
        VALUES (?, ?, ?)
    """, rows)

    print(
        con.execute("""
            SELECT
                COUNT(*) AS sessions,
                MIN(session_date) AS first_session,
                MAX(session_date) AS last_session
            FROM silver.trading_calendar
        """).fetchall()
    )

    con.close()


if __name__ == "__main__":
    main()
