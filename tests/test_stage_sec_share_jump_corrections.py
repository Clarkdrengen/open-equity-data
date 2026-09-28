import duckdb

import open_equity_data.stage_sec_share_jump_corrections as module

stage = module.stage


def test_source_preview_is_dated_and_only_targets_flagged_rows():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.eodhd_share_jump_guard_impact_candidate AS
        SELECT security_id, ticker, date, filing AS shares_filing_date,
               shares AS eodhd_filed_shares,
               shares * 16 AS original_cap, 40000000.0 AS dry_run_cap,
               16.0 AS close
        FROM (VALUES
            (7462, 'FRST', DATE '2021-08-08', DATE '2021-10-27', 24539369000.0),
            (7462, 'FRST', DATE '2021-10-28', DATE '2021-10-27', 24539369000.0),
            (7462, 'FRST', DATE '2021-11-10', DATE '2021-10-27', 24539369000.0),
            (6487, 'EVBN', DATE '2013-03-04', DATE '2013-03-04', 4171473000.0),
            (6487, 'EVBN', DATE '2013-03-05', DATE '2013-03-04', 4171473000.0)
        ) v(security_id, ticker, date, filing, shares)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, ticker, date, shares_filing_date,
               eodhd_filed_shares, eodhd_filed_shares AS eodhd_normalized_shares,
               DATE '2021-09-30' AS shares_period_date,
               ticker || '.US' AS eodhd_provider_symbol,
               'eodhd' AS selected_source
        FROM silver.eodhd_share_jump_guard_impact_candidate
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT 7462 AS security_id, 'FRST' AS ticker,
               'Primis Financial Corp.' AS bronze_security_name
        UNION ALL
        SELECT 6487, 'EVBN', 'Evans Bancorp, Inc.'
    """)
    rows = stage(con)
    assert {r[1]: r[3] for r in rows} == {
        '0001193125-12-448401': 1, '0001562762-13-000070': 1,
        '0001558370-21-010914': 1, '0001558370-21-015243': 1}
    assert con.execute("""
        SELECT COUNT(*) FROM sec_share_jump_correction_preview
        WHERE proposed_cap < original_cap
    """).fetchone()[0] == 4


def test_apply_exact_reviewed_rows_through_bronze_then_silver(monkeypatch):
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TEMP TABLE sec_share_jump_correction_preview AS
        SELECT security_id, ticker, price_date,
               ticker || '.US' AS target_provider_symbol,
               DATE '2020-12-31' AS target_period_date,
               DATE '2021-01-02' AS target_filing_date,
               10000000000.0 AS target_shares,
               10000000.0 AS sourced_shares,
               DATE '2021-01-01' AS shares_as_of_date,
               DATE '2021-01-02' AS source_publication_date,
               'SEC cover page' AS source_name,
               'https://www.sec.gov/example' AS source_url,
               source_document_id,
               '10,000,000 shares outstanding' AS source_excerpt
        FROM (VALUES
            (6487, 'EVBN', DATE '2021-01-04', '0001193125-12-448401'),
            (6487, 'EVBN', DATE '2021-01-05', '0001562762-13-000070'),
            (7462, 'FRST', DATE '2021-01-04', '0001558370-21-010914'),
            (7462, 'FRST', DATE '2021-01-05', '0001558370-21-015243'),
            (11532, 'LHC', DATE '2021-01-04', '0001193125-19-290000')
        ) v(security_id, ticker, price_date, source_document_id)
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, price_date AS date, 'eodhd' AS selected_source,
               10000000000.0 AS selected_shares_candidate
        FROM sec_share_jump_correction_preview
    """)
    def rebuild(conn, *, manage_transaction):
        assert not manage_transaction
        conn.execute("""
            UPDATE silver.security_daily_market_cap_source_priority_candidate c
            SET selected_source = 'manual_sourced',
                selected_shares_candidate = s.sourced_shares
            FROM sec_share_jump_correction_preview s
            WHERE c.security_id = s.security_id AND c.date = s.price_date
        """)
    monkeypatch.setattr(module, 'build', rebuild)
    docs = con.execute("""
        SELECT DISTINCT source_document_id
        FROM sec_share_jump_correction_preview
    """).fetchall()
    rows = [(None, doc, None, 1, None, None, None, None, 1)
            for (doc,) in docs]
    module.apply(con, rows)
    assert con.execute("""
        SELECT COUNT(*) FROM bronze.eodhd_share_manual_adjustment
    """).fetchone()[0] == 5
    assert con.execute("""
        SELECT COUNT(*) FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE selected_source = 'manual_sourced'
    """).fetchone()[0] == 5
