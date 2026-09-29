import hashlib
import json
from datetime import date
from pathlib import Path

import duckdb

from open_equity_data.recover_eodhd_bulk_price_gaps import SESSIONS, build


def test_exact_adjacent_identity_and_bronze_integrity():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA bronze")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE bronze.eodhd_bulk_eod_response (
            requested_date DATE, raw_response_bytes BLOB, response_sha256 VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv (
            date DATE, security_id BIGINT, identity_status VARCHAR,
            lineage_id BIGINT, lineage_code VARCHAR, ticker VARCHAR,
            close DOUBLE, research_eligible BOOLEAN, source_lookup_method VARCHAR
        )
    """)
    con.execute("CREATE TABLE silver.clean_ohlcv (date DATE, act_symbol VARCHAR)")

    for session, (before, after) in SESSIONS.items():
        for d in (before, after):
            for sid, ticker in [(1, "AAPL"), (2, "BAD"), (3, "NATIVE"), (4, "BRK.A")]:
                con.execute("""
                    INSERT INTO silver.security_daily_ohlcv
                    VALUES (?, ?, 'singleton_episode', NULL, NULL, ?, 100, TRUE, 'native')
                """, [d, sid, ticker])
        con.execute("INSERT INTO silver.clean_ohlcv VALUES (?, 'NATIVE')", [session])
        rows = [
            dict(date=session.isoformat(), code=ticker, open=100,
                 high=10010 if ticker == "BAD" else 102,
                 low=99, close=close, volume=1000)
            for ticker, close in [("AAPL", 101), ("BAD", 10000),
                                  ("NATIVE", 101), ("BRK-A", 101)]
        ]
        raw = json.dumps(rows).encode()
        con.execute("INSERT INTO bronze.eodhd_bulk_eod_response VALUES (?, ?, ?)",
                    [session, raw, hashlib.sha256(raw).hexdigest()])

    summary = build(con)
    assert (date(2019, 8, 23), "candidate_usable", 2, 2) in summary
    assert (date(2019, 8, 23), "price_basis_review", 1, 1) in summary
    assert con.execute("""
        SELECT COUNT(*) FROM silver.eodhd_bulk_missing_price_candidate
        WHERE ticker = 'NATIVE'
    """).fetchone()[0] == 0
    assert con.execute("""
        SELECT provider_code FROM silver.eodhd_bulk_missing_price_candidate
        WHERE ticker = 'BRK.A' AND date = DATE '2019-08-23'
    """).fetchone() == ("BRK-A",)
    assert summary == build(con)

    # Canonical price rebuild consumes the derived candidate without altering
    # native observations or admitting a price-basis mismatch.
    for column in ("open", "high", "low", "close"):
        con.execute(f"ALTER TABLE silver.clean_ohlcv ADD COLUMN {column} DOUBLE")
    con.execute("ALTER TABLE silver.clean_ohlcv ADD COLUMN volume BIGINT")
    con.execute("UPDATE silver.clean_ohlcv SET open=100, high=102, low=99, close=100, volume=1000")
    con.execute("""
        CREATE TABLE silver.reconciled_ohlcv (
            lineage_id BIGINT, lineage_code VARCHAR, date DATE, ticker VARCHAR,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT,
            source VARCHAR, source_symbol VARCHAR, source_lookup_method VARCHAR,
            reconciliation_status VARCHAR, observation_type VARCHAR,
            research_eligible BOOLEAN
        )
    """)
    con.execute("CREATE TABLE silver.security_master (security_id BIGINT, lineage_id BIGINT, identity_status VARCHAR)")
    con.execute("CREATE TABLE silver.ticker_episode (ticker_episode_id BIGINT, act_symbol VARCHAR, start_date DATE, end_date DATE)")
    con.execute("CREATE TABLE silver.security_episode_membership (ticker_episode_id BIGINT, security_id BIGINT)")
    for sid, ticker in [(1, "AAPL"), (2, "BAD"), (3, "NATIVE"), (4, "BRK.A")]:
        con.execute("INSERT INTO silver.security_master VALUES (?, NULL, 'singleton_episode')", [sid])
        con.execute("INSERT INTO silver.ticker_episode VALUES (?, ?, DATE '2019-01-01', DATE '2019-12-31')", [sid, ticker])
        con.execute("INSERT INTO silver.security_episode_membership VALUES (?, ?)", [sid, sid])
    canonical_sql = Path("sql/silver/create_security_daily_ohlcv.sql").read_text()
    con.execute(canonical_sql)
    assert con.execute("""
        SELECT ticker, source FROM silver.security_daily_ohlcv
        WHERE date = DATE '2019-08-23' ORDER BY ticker
    """).fetchall() == [("AAPL", "eodhd"), ("BRK.A", "eodhd"), ("NATIVE", "dolt")]
    assert con.execute("""
        SELECT source_symbol FROM silver.security_daily_ohlcv
        WHERE ticker = 'BRK.A' AND date = DATE '2019-08-23'
    """).fetchone() == ("BRK-A.US",)

    con.execute("""
        UPDATE bronze.eodhd_bulk_eod_response
        SET response_sha256 = 'bad' WHERE requested_date = DATE '2019-08-23'
    """)
    try:
        build(con)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("changed Bronze bytes were accepted")
