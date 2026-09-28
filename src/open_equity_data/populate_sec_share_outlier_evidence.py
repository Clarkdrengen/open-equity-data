"""Stage two SEC cover-page share counts against exact suspect EODHD records.

Preview is the default. --apply appends dated Bronze evidence and rebuilds the
Silver candidate transactionally. It does not rescale the vendor's raw facts.
"""

from __future__ import annotations

import argparse

from open_equity_data.build_msci_daily_share_preference import (
    MANUAL_SCHEMA,
    build,
    top_eodhd_outliers,
)
from open_equity_data.db import connect


DOCUMENT_IDS = ('0001528930-21-000048', '0001213900-21-011788')

STAGE_SQL = """
CREATE OR REPLACE TEMP TABLE sec_share_outlier_stage AS
WITH evidence AS (
    SELECT * FROM (VALUES
        (7430, 'FRG', DATE '2021-11-02', DATE '2021-11-03',
         DATE '2021-10-29', 40295469.0, 40973736000.0,
         '0001528930-21-000048',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893021000048/frg-20210925.htm',
         '40,295,469 shares outstanding as of October 29, 2021'),
        (9376, 'HYLN', DATE '2021-02-26', DATE '2021-02-26',
         DATE '2021-02-23', 170255200.0, 104324059000.0,
         '0001213900-21-011788',
         'https://www.sec.gov/Archives/edgar/data/1759631/000121390021011788/f10k2020_hyliionholdings.htm',
         '170,255,200 shares outstanding as of February 23, 2021')
    ) AS e(security_id, ticker, publication_date, first_price_date,
           shares_as_of_date, sourced_shares, target_shares,
           source_document_id, source_url, source_excerpt)
), priced AS (
    SELECT e.*, p.date AS price_date
    FROM evidence e
    JOIN silver.security_daily_ohlcv_reconciled p
      ON p.security_id = e.security_id AND p.ticker = e.ticker
     AND p.date >= e.first_price_date
     AND date_diff('day', e.publication_date, p.date) <= 365
), attached AS (
    SELECT p.*, o.provider_symbol, o.period_date, o.filing_date,
           o.shares_outstanding,
           r.bronze_security_name
    FROM priced p
    ASOF LEFT JOIN silver.security_shares_outstanding_effective o
      ON p.ticker = o.ticker AND p.price_date >= o.filing_date
    LEFT JOIN silver.security_ticker_reference_resolution r
      ON r.security_id = p.security_id AND r.ticker = p.ticker
)
SELECT security_id, ticker, price_date,
       provider_symbol AS target_provider_symbol,
       period_date AS target_period_date,
       filing_date AS target_filing_date,
       shares_outstanding AS target_shares,
       sourced_shares, shares_as_of_date, publication_date AS source_publication_date,
       'SEC Form 10-Q/10-K cover page' AS source_name, source_url,
       source_document_id, source_excerpt
FROM attached
WHERE shares_outstanding = target_shares
  AND provider_symbol = ticker || '.US'
  AND ((ticker = 'FRG' AND UPPER(bronze_security_name) LIKE '%FRANCHISE GROUP%')
    OR (ticker = 'HYLN' AND UPPER(bronze_security_name) LIKE '%HYLIION%'))
"""


def stage(con):
    con.execute(STAGE_SQL)
    summary = con.execute("""
        SELECT ticker, source_document_id, sourced_shares, target_shares,
               COUNT(*) AS price_days, MIN(price_date), MAX(price_date),
               COUNT(DISTINCT (target_provider_symbol, target_period_date,
                               target_filing_date, target_shares)) AS targets
        FROM sec_share_outlier_stage
        GROUP BY 1, 2, 3, 4 ORDER BY 1
    """).fetchall()
    if len(summary) != 2 or any(row[4] == 0 for row in summary):
        raise ValueError(f"Expected both exact EODHD targets; got {summary}")
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
          AND source_document_id NOT IN (?, ?) LIMIT 1
    """, list(DOCUMENT_IDS)).fetchone()
    if existing:
        raise ValueError(f"Another sourced adjustment already exists: {existing}")
    con.execute('BEGIN TRANSACTION')
    try:
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment
            WHERE security_id IN (7430, 9376)
              AND source_document_id IN (?, ?)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with connect() as con:
        con.execute(MANUAL_SCHEMA.read_text())
        for row in stage(con):
            print('ticker | SEC accession | filed shares | raw EODHD shares | dates | first | last | targets')
            print(*row, sep=' | ')
        if args.apply:
            print('Rebuilt selected sources:', apply(con))
            print('Remaining largest EODHD cap candidates (review queue):')
            for row in top_eodhd_outliers(con, 20):
                print(*row, sep=' | ')
        else:
            print('Preview only; run with --apply to populate dated Bronze and rebuild Silver.')


if __name__ == '__main__':
    main()
