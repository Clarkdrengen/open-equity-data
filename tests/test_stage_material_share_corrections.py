from datetime import date

import duckdb
import pytest

import open_equity_data.stage_material_share_corrections as module
from open_equity_data.build_msci_daily_share_preference import MANUAL_SCHEMA


def _connection():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute(MANUAL_SCHEMA.read_text())
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT security_id, ticker, date, 8.0 AS close,
               8.0 * raw_shares AS market_cap_candidate,
               ticker || '.US' AS eodhd_provider_symbol,
               DATE '2011-03-31' AS shares_period_date,
               DATE '2011-05-05' AS shares_filing_date,
               raw_shares AS eodhd_filed_shares,
               1.0 AS current_split_multiplier,
               1.0 AS period_split_multiplier,
               TRUE AS price_research_eligible,
               'eodhd' AS selected_source,
               NULL::VARCHAR AS manual_document_id,
               raw_shares AS selected_shares_candidate
        FROM (VALUES
            (7430, 'FRG', DATE '2020-09-17', 34972364000.0),
            (2527, 'BLW', DATE '2011-06-29', 29043000000.0),
            (5988, 'ELLO', DATE '2011-06-08', 86102748000.0),
            (5988, 'ELLO', DATE '2011-06-17', 86102748000.0)
        ) v(security_id, ticker, date, raw_shares)
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT * FROM (VALUES
            (7430, 'FRG', 'Franchise Group, Inc.'),
            (2527, 'BLW', 'Blackrock Limited Duration Income Trust'),
            (5988, 'ELLO', 'Ellomay Capital Ltd.')
        ) v(security_id, ticker, bronze_security_name)
    """)
    return con


def test_stage_excludes_pre_effective_ello_and_targets_exact_facts():
    con = _connection()
    rows = module.stage(con)
    assert [(r[0], r[3]) for r in rows] == [
        ('BLW', 1), ('ELLO', 1), ('FRG', 1)]
    assert con.execute("""
        SELECT ticker, price_date, sourced_shares
        FROM material_share_correction_stage ORDER BY ticker
    """).fetchall() == [
        ('BLW', date(2011, 6, 29), 36908388.0),
        ('ELLO', date(2011, 6, 17), 10777850.0),
        ('FRG', date(2020, 9, 17), 40029599.0),
    ]


def test_apply_writes_bronze_and_rebuilds_silver_atomically(monkeypatch):
    con = _connection()
    module.stage(con)
    con.execute("""
        INSERT INTO bronze.eodhd_share_manual_adjustment (
            security_id, ticker, sourced_shares, shares_as_of_date,
            source_publication_date, source_name, source_url,
            source_document_id, source_excerpt, recorded_at, price_date)
        VALUES (9376, 'HYLN', 170255200, DATE '2021-02-23',
                DATE '2021-02-26', 'SEC', 'https://sec.gov/hyln',
                'existing', '170,255,200', current_timestamp,
                DATE '2021-02-26')
    """)

    def rebuild(conn, *, manage_transaction):
        assert manage_transaction is False
        conn.execute("""
            UPDATE silver.security_daily_market_cap_source_priority_candidate c
               SET selected_source = 'manual_sourced',
                   selected_shares_candidate = s.sourced_shares,
                   manual_document_id = s.source_document_id,
                   market_cap_candidate = c.close * s.sourced_shares
              FROM material_share_correction_stage s
             WHERE c.security_id = s.security_id AND c.date = s.price_date
               AND EXISTS (
                   SELECT 1 FROM bronze.eodhd_share_manual_adjustment b
                   WHERE b.security_id = s.security_id
                     AND b.price_date = s.price_date)
        """)
    monkeypatch.setattr(module, 'build', rebuild)
    result = module.apply(con)
    assert [r[:2] for r in result] == [
        ('BLW', 1), ('ELLO', 1), ('FRG', 1)]
    assert con.execute("""
        SELECT COUNT(*) FROM bronze.eodhd_share_manual_adjustment
    """).fetchone()[0] == 4
    assert con.execute("""
        SELECT COUNT(*) FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE selected_source = 'manual_sourced'
    """).fetchone()[0] == 3
    assert module.apply(con) == result


def test_failed_rebuild_rolls_back_bronze(monkeypatch):
    con = _connection()
    module.stage(con)

    def failing_rebuild(conn, *, manage_transaction):
        raise ValueError('rebuild failure')

    monkeypatch.setattr(module, 'build', failing_rebuild)
    with pytest.raises(ValueError, match='rebuild failure'):
        module.apply(con)
    assert con.execute("""
        SELECT COUNT(*) FROM bronze.eodhd_share_manual_adjustment
    """).fetchone()[0] == 0
