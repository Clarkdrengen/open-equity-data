import duckdb

from open_equity_data.stage_sec_share_jump_corrections import stage


def test_source_preview_is_dated_and_only_targets_flagged_rows():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.eodhd_share_jump_guard_impact_candidate AS
        SELECT 7462 AS security_id, 'FRST' AS ticker, date,
               DATE '2021-10-27' AS shares_filing_date,
               24539369000.0 AS eodhd_filed_shares,
               402000000000.0 AS original_cap, 40000000.0 AS dry_run_cap,
               16.0 AS close
        FROM (VALUES (DATE '2021-08-08'), (DATE '2021-10-28'),
                     (DATE '2021-11-10')) v(date)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, ticker, date, shares_filing_date,
               eodhd_filed_shares, eodhd_filed_shares AS eodhd_normalized_shares,
               DATE '2021-09-30' AS shares_period_date,
               'FRST.US' AS eodhd_provider_symbol, 'eodhd' AS selected_source
        FROM silver.eodhd_share_jump_guard_impact_candidate
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT 7462 AS security_id, 'FRST' AS ticker,
               'Primis Financial Corp.' AS bronze_security_name
    """)
    rows = stage(con)
    assert [(r[1], r[3]) for r in rows] == [
        ('0001558370-21-010914', 1), ('0001558370-21-015243', 1)]
    assert con.execute("""
        SELECT COUNT(*) FROM sec_share_jump_correction_preview
        WHERE proposed_cap < original_cap
    """).fetchone()[0] == 2
