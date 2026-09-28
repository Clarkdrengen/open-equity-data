"""Carry dated SEC cover-page share proxies and flag gross EODHD mismatches.

Preview is the default. --apply appends dated Bronze evidence and rebuilds the
Silver candidate transactionally. It does not rescale the vendor's raw facts.
"""

from __future__ import annotations

import argparse
from datetime import date

from open_equity_data.build_msci_daily_share_preference import (
    MANUAL_SCHEMA,
    build,
    top_eodhd_outliers,
)
from open_equity_data.db import connect


DOCUMENT_IDS = (
    '0001528930-20-000070',
    '0001528930-21-000043', '0001528930-21-000048',
    '0001528930-22-000046',
    '0001213900-21-011788',
)
FRG_2022_DOCUMENT_ID = '0001528930-22-000046'

STAGE_SQL = """
CREATE OR REPLACE TEMP TABLE sec_share_outlier_stage AS
WITH evidence AS (
    SELECT * FROM (VALUES
        (7430, 'FRG', DATE '2020-11-04', DATE '2020-11-05',
         DATE '2020-11-02', 40087792.0, 39692384000.0,
         '0001528930-20-000070',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893020000070/frg-0926202010q.htm',
         '40,087,792 shares outstanding as of November 2, 2020'),
        (7430, 'FRG', DATE '2021-08-03', DATE '2021-08-04',
         DATE '2021-07-30', 40228467.0, 40905567000.0,
         '0001528930-21-000043',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893021000043/frg-20210626.htm',
         '40,228,467 shares outstanding as of July 30, 2021'),
        (7430, 'FRG', DATE '2021-11-02', DATE '2021-11-03',
         DATE '2021-10-29', 40295469.0, 40973736000.0,
         '0001528930-21-000048',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893021000048/frg-20210925.htm',
         '40,295,469 shares outstanding as of October 29, 2021'),
        (7430, 'FRG', DATE '2022-11-03', DATE '2022-11-04',
         DATE '2022-10-31', 38205831.0, 39941287000.0,
         '0001528930-22-000046',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893022000046/frg-20220924.htm',
         '38,205,831 shares outstanding as of October 31, 2022'),
        (9376, 'HYLN', DATE '2021-02-26', DATE '2021-02-26',
         DATE '2021-02-23', 170255200.0, 104324059000.0,
         '0001213900-21-011788',
         'https://www.sec.gov/Archives/edgar/data/1759631/000121390021011788/f10k2020_hyliionholdings.htm',
         '170,255,200 shares outstanding as of February 23, 2021')
    ) AS e(security_id, ticker, publication_date, first_price_date,
           shares_as_of_date, sourced_shares, initially_bad_shares,
           source_document_id, source_url, source_excerpt)
), priced AS (
    SELECT e.*, p.date AS price_date
    FROM evidence e
    JOIN silver.security_daily_ohlcv_reconciled p
      ON p.security_id = e.security_id AND p.ticker = e.ticker
     AND p.date >= e.first_price_date
     AND date_diff('day', e.publication_date, p.date) <= 365
), latest_source AS (
    SELECT * FROM priced
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY security_id, price_date
        ORDER BY publication_date DESC
    ) = 1
), attached AS (
    SELECT p.*, o.provider_symbol, o.period_date, o.filing_date,
           o.shares_outstanding AS observed_shares,
           r.bronze_security_name
    FROM latest_source p
    ASOF LEFT JOIN silver.security_shares_outstanding_effective o
      ON p.ticker = o.ticker AND p.price_date >= o.filing_date
    LEFT JOIN silver.security_ticker_reference_resolution r
      ON r.security_id = p.security_id AND r.ticker = p.ticker
)
SELECT security_id, ticker, price_date,
       CASE WHEN provider_symbol = ticker || '.US'
                      AND observed_shares >= sourced_shares * 100
            THEN provider_symbol END AS target_provider_symbol,
       CASE WHEN provider_symbol = ticker || '.US'
                      AND observed_shares >= sourced_shares * 100
            THEN period_date END AS target_period_date,
       CASE WHEN provider_symbol = ticker || '.US'
                      AND observed_shares >= sourced_shares * 100
            THEN filing_date END AS target_filing_date,
       CASE WHEN provider_symbol = ticker || '.US'
                      AND observed_shares >= sourced_shares * 100
            THEN observed_shares END AS target_shares,
       sourced_shares, shares_as_of_date, publication_date AS source_publication_date,
       'SEC Form 10-Q/10-K cover page' AS source_name, source_url,
       source_document_id, source_excerpt
FROM attached
WHERE ((ticker = 'FRG' AND UPPER(bronze_security_name) LIKE '%FRANCHISE GROUP%')
    OR (ticker = 'HYLN' AND UPPER(bronze_security_name) LIKE '%HYLIION%'))
"""


def stage(con):
    con.execute(STAGE_SQL)
    summary = con.execute("""
        SELECT ticker, source_document_id, sourced_shares,
               COUNT(*) AS price_days, MIN(price_date), MAX(price_date),
               COUNT(DISTINCT (target_provider_symbol, target_period_date,
                               target_filing_date, target_shares))
                   FILTER (WHERE target_shares IS NOT NULL) AS targets,
               COUNT(*) FILTER (WHERE target_shares IS NOT NULL)
                   AS flagged_issue_days
        FROM sec_share_outlier_stage
        GROUP BY 1, 2, 3 ORDER BY 1, 5
    """).fetchall()
    if len(summary) != 5 or any(row[3] == 0 or row[6] == 0 for row in summary):
        raise ValueError(f"Expected five sourced cohorts and bad EODHD targets; got {summary}")
    initial = con.execute("""
        SELECT ticker, target_shares FROM sec_share_outlier_stage
        WHERE (ticker = 'FRG' AND target_shares IN
                   (39692384000.0, 40905567000.0, 40973736000.0,
                    39941287000.0))
           OR (ticker = 'HYLN' AND target_shares = 104324059000.0)
        GROUP BY ticker, target_shares ORDER BY ticker, target_shares
    """).fetchall()
    if initial != [
        ('FRG', 39692384000.0), ('FRG', 39941287000.0),
        ('FRG', 40905567000.0), ('FRG', 40973736000.0),
        ('HYLN', 104324059000.0),
    ]:
        raise ValueError(f"Original source observations missing: {initial}")
    duplicate = con.execute("""
        SELECT security_id, price_date, COUNT(*) FROM sec_share_outlier_stage
        GROUP BY 1, 2 HAVING COUNT(*) > 1 LIMIT 1
    """).fetchone()
    if duplicate:
        raise ValueError(f"Duplicate target date: {duplicate}")
    return summary


def apply(con):
    existing = con.execute("""
        SELECT security_id, ticker, price_date, source_document_id
        FROM bronze.eodhd_share_manual_adjustment
        WHERE security_id IN (7430, 9376)
          AND source_document_id NOT IN (?, ?, ?, ?, ?) LIMIT 1
    """, list(DOCUMENT_IDS)).fetchone()
    if existing:
        raise ValueError(f"Another sourced adjustment already exists: {existing}")
    con.execute('BEGIN TRANSACTION')
    try:
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment
            WHERE security_id IN (7430, 9376)
              AND source_document_id IN (?, ?, ?, ?, ?)
        """, list(DOCUMENT_IDS))
        con.execute("""
            INSERT INTO bronze.eodhd_share_manual_adjustment (
                security_id, ticker, price_date, target_provider_symbol,
                target_period_date, target_filing_date, target_shares,
                sourced_shares, shares_as_of_date, source_publication_date,
                source_name, source_url, source_document_id, source_excerpt,
                source_document_sha256, recorded_at)
            SELECT security_id, ticker, price_date, target_provider_symbol,
                   target_period_date, target_filing_date, target_shares,
                   sourced_shares, shares_as_of_date, source_publication_date,
                   source_name, source_url, source_document_id, source_excerpt,
                   NULL, current_timestamp
            FROM sec_share_outlier_stage
        """)
        build(con, manage_transaction=False)
        result = con.execute("""
            SELECT ticker, selected_source, COUNT(*) AS issue_days,
                   MAX(market_cap_candidate) AS max_cap
            FROM silver.security_daily_market_cap_source_priority_candidate
            WHERE (security_id, date) IN
                (SELECT security_id, price_date FROM sec_share_outlier_stage)
            GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
        con.execute('COMMIT')
        return result
    except Exception:
        con.execute('ROLLBACK')
        raise


def apply_frg_2022(con):
    """Apply only the approved November 2022 FRG cohort; retain prior rows."""
    con.execute(MANUAL_SCHEMA.read_text())
    preview = con.execute("""
        SELECT COUNT(*), MIN(price_date), MAX(price_date),
               COUNT(*) FILTER (WHERE target_shares = 39941287000.0)
        FROM sec_share_outlier_stage
        WHERE security_id = 7430 AND ticker = 'FRG'
          AND source_document_id = ? AND sourced_shares = 38205831.0
          AND source_publication_date = DATE '2022-11-03'
    """, [FRG_2022_DOCUMENT_ID]).fetchone()
    if preview[0] < 1 or preview[1] != date(2022, 11, 4) or preview[3] < 1:
        raise ValueError(f'Incomplete FRG 2022 preview: {preview}')
    conflict = con.execute("""
        SELECT a.price_date, a.source_document_id
        FROM bronze.eodhd_share_manual_adjustment a
        JOIN sec_share_outlier_stage s
          ON a.security_id = s.security_id AND a.price_date = s.price_date
        WHERE s.source_document_id = ?
          AND a.source_document_id <> s.source_document_id
        LIMIT 1
    """, [FRG_2022_DOCUMENT_ID]).fetchone()
    if conflict:
        raise ValueError(f'Existing dated Bronze adjustment conflicts: {conflict}')
    con.execute('BEGIN TRANSACTION')
    try:
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment
            WHERE security_id = 7430 AND source_document_id = ?
        """, [FRG_2022_DOCUMENT_ID])
        con.execute("""
            INSERT INTO bronze.eodhd_share_manual_adjustment (
                security_id, ticker, price_date, target_provider_symbol,
                target_period_date, target_filing_date, target_shares,
                sourced_shares, shares_as_of_date, source_publication_date,
                source_name, source_url, source_document_id, source_excerpt,
                source_document_sha256, recorded_at)
            SELECT security_id, ticker, price_date, target_provider_symbol,
                   target_period_date, target_filing_date, target_shares,
                   sourced_shares, shares_as_of_date, source_publication_date,
                   source_name, source_url, source_document_id, source_excerpt,
                   NULL, current_timestamp
            FROM sec_share_outlier_stage WHERE source_document_id = ?
        """, [FRG_2022_DOCUMENT_ID])
        build(con, manage_transaction=False)
        mismatch = con.execute("""
            SELECT s.price_date, c.selected_source, c.selected_shares_candidate
            FROM sec_share_outlier_stage s
            LEFT JOIN silver.security_daily_market_cap_source_priority_candidate c
              ON c.security_id = s.security_id AND c.date = s.price_date
            WHERE s.source_document_id = ?
              AND (c.security_id IS NULL OR c.selected_source <> 'manual_sourced'
                   OR c.selected_shares_candidate <> s.sourced_shares)
            LIMIT 1
        """, [FRG_2022_DOCUMENT_ID]).fetchone()
        if mismatch:
            raise ValueError(f'FRG 2022 Silver selection mismatch: {mismatch}')
        result = con.execute("""
            SELECT COUNT(*), MIN(c.date), MAX(c.date), MAX(c.market_cap_candidate)
            FROM silver.security_daily_market_cap_source_priority_candidate c
            JOIN sec_share_outlier_stage s
              ON s.security_id = c.security_id AND s.price_date = c.date
            WHERE s.source_document_id = ?
        """, [FRG_2022_DOCUMENT_ID]).fetchone()
        con.execute('COMMIT')
        return result
    except Exception:
        con.execute('ROLLBACK')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--apply-frg-2022', action='store_true',
                      help='Only apply the November 2022 FRG SEC cohort')
    args = parser.parse_args()
    with connect() as con:
        con.execute(MANUAL_SCHEMA.read_text())
        print('ticker | SEC accession | sourced shares | dates | first | last | bad EODHD records | flagged dates')
        for row in stage(con):
            print(*row, sep=' | ')
        if args.apply_frg_2022:
            print('FRG 2022 selected days | first | last | peak cap:',
                  apply_frg_2022(con))
        elif args.apply:
            print('Rebuilt selected sources:', apply(con))
            print('Remaining largest EODHD cap candidates (review queue):')
            for row in top_eodhd_outliers(con, 20):
                print(*row, sep=' | ')
        else:
            print('Preview only; run with --apply to populate dated Bronze and rebuild Silver.')


if __name__ == '__main__':
    main()
