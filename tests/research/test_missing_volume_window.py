from datetime import date, timedelta
from pathlib import Path

import duckdb


def test_missing_volume_does_not_become_zero_or_shrink_rolling_window():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.security_daily_return_research (
            security_id BIGINT, date DATE, ticker VARCHAR,
            gross_total_return DOUBLE, price_return DOUBLE,
            split_normalized_close DOUBLE, final_research_eligible BOOLEAN
        );
        CREATE TABLE silver.security_gtr_index (
            security_id BIGINT, date DATE, return_segment_id BIGINT
        );
        CREATE TABLE silver.security_daily_ohlcv_reconciled (
            security_id BIGINT, date DATE, volume DOUBLE
        );
        CREATE TABLE silver.research_market_daily (
            date DATE, market_return_1d DOUBLE
        );
        CREATE TABLE silver.research_universe_eligibility (
            security_id BIGINT, date DATE,
            primary_research_eligible_broad BOOLEAN,
            primary_research_eligible_exchange BOOLEAN
        );
        CREATE TABLE silver.security_forward_return_label AS
        SELECT 1::BIGINT AS security_id, DATE '2020-01-01' AS date,
               NULL::DOUBLE AS security_forward_return_1d,
               NULL::DOUBLE AS security_forward_return_5d,
               NULL::DOUBLE AS security_forward_return_10d,
               NULL::DOUBLE AS security_forward_return_20d,
               NULL::DOUBLE AS security_forward_return_60d
        WHERE FALSE;
        CREATE TABLE silver.research_market_forward_return AS
        SELECT DATE '2020-01-01' AS date,
               NULL::DOUBLE AS market_forward_return_1d,
               NULL::DOUBLE AS market_forward_return_5d,
               NULL::DOUBLE AS market_forward_return_10d,
               NULL::DOUBLE AS market_forward_return_20d,
               NULL::DOUBLE AS market_forward_return_60d
        WHERE FALSE;
    """)
    start = date(2020, 1, 1)
    rows = [(start + timedelta(days=i), None if i == 10 else 100 + i * i)
            for i in range(35)]
    con.executemany("""
        INSERT INTO silver.security_daily_return_research
        VALUES (1, ?, 'AAA', 0.01, 0.01, 10.0, TRUE)
    """, [(d,) for d, _ in rows])
    con.executemany("INSERT INTO silver.security_gtr_index VALUES (1, ?, 0)",
                    [(d,) for d, _ in rows])
    con.executemany("INSERT INTO silver.security_daily_ohlcv_reconciled VALUES (1, ?, ?)",
                    rows)
    con.executemany("INSERT INTO silver.research_market_daily VALUES (?, 0.0)",
                    [(d,) for d, _ in rows])
    con.executemany("""
        INSERT INTO silver.research_universe_eligibility
        VALUES (1, ?, TRUE, TRUE)
    """, [(d,) for d, _ in rows])

    sql = (Path(__file__).resolve().parents[2] / "sql/silver/create_research_feature_table.sql").read_text()
    con.execute(sql[sql.index("-- 4. Feature source"):])

    missing_day = con.execute("""
        SELECT log_volume FROM silver.research_feature_source WHERE date = ?
    """, [rows[10][0]]).fetchone()[0]
    incomplete = con.execute("""
        SELECT relative_volume_20d, volume_zscore_20d, trailing_gtr_20d
        FROM silver.research_feature_label WHERE date = ?
    """, [rows[21][0]]).fetchone()
    complete = con.execute("""
        SELECT relative_volume_20d, volume_zscore_20d
        FROM silver.research_feature_label WHERE date = ?
    """, [rows[31][0]]).fetchone()
    assert missing_day is None
    assert incomplete[0] is None and incomplete[1] is None
    assert incomplete[2] is not None  # Price/return history remains intact.
    assert complete[0] is not None and complete[1] is not None
    con.close()
