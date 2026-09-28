"""Stage three source-backed, dated share corrections for domain review.

Preview is read-only. --apply writes only to the Bronze sourced-adjustment
table and rebuilds the derived Silver market-cap candidate transactionally.
No issue classification or source vendor record is rewritten.
"""

import argparse

from open_equity_data.build_msci_daily_share_preference import (
    build,
    top_eodhd_outliers,
)
from open_equity_data.db import connect


DOCUMENT_IDS = (
    'FRG_2020-08-05_10Q',
    'BLW_2011-06-16_DEF14A',
    'ELLO_2011-06-02_split_announcement',
)

STAGE_SQL = """
CREATE OR REPLACE TEMP TABLE material_share_correction_stage AS
WITH evidence AS (
    SELECT * FROM (VALUES
        (7430, 'FRG', DATE '2020-08-05', DATE '2020-08-06',
         DATE '2020-08-03', 40029599.0,
         'FRG_2020-08-05_10Q', 'SEC Form 10-Q',
         'https://www.sec.gov/Archives/edgar/data/1528930/000152893020000057/frg-0627202010q.htm',
         '40,029,599 common shares as of August 3, 2020'),
        (2527, 'BLW', DATE '2011-06-16', DATE '2011-06-17',
         DATE '2011-05-31', 36908388.0,
         'BLW_2011-06-16_DEF14A', 'SEC definitive proxy statement',
         'https://www.sec.gov/Archives/edgar/data/1137393/000089109211003940/e43993def14a.htm',
         '36,908,388 common shares outstanding as of May 31, 2011'),
        (5988, 'ELLO', DATE '2011-06-02', DATE '2011-06-09',
         DATE '2011-06-02', 10777850.0,
         'ELLO_2011-06-02_split_announcement',
         'Issuer reverse-split announcement (expected post-split proxy)',
         'https://www.prnewswire.com/news-releases/ellomay-capital-announces-a-one-for-ten-reverse-split-123034353.html',
         'Expected approximately 10,777,850 post-split shares effective June 9, 2011')
    ) AS e(security_id, ticker, publication_date, first_price_date,
           shares_as_of_date, sourced_shares, source_document_id,
           source_name, source_url, source_excerpt)
), candidate AS (
    SELECT e.*, c.date AS price_date, c.close,
           c.close * c.eodhd_filed_shares AS original_cap,
           c.eodhd_provider_symbol AS target_provider_symbol,
           c.shares_period_date AS target_period_date,
           c.shares_filing_date AS target_filing_date,
           c.eodhd_filed_shares AS target_shares,
           c.current_split_multiplier, c.period_split_multiplier,
           c.price_research_eligible,
           r.bronze_security_name
    FROM evidence e
    JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = e.security_id AND c.ticker = e.ticker
     AND c.date >= e.first_price_date
     AND date_diff('day', e.publication_date, c.date) <= 365
     AND (c.selected_source = 'eodhd'
          OR (c.selected_source = 'manual_sourced'
              AND c.manual_document_id = e.source_document_id))
     AND c.eodhd_filed_shares >= 100 * e.sourced_shares
    JOIN silver.security_ticker_reference_resolution r
      ON r.security_id = e.security_id AND r.ticker = e.ticker
    WHERE (e.ticker = 'FRG' AND UPPER(r.bronze_security_name) LIKE '%FRANCHISE GROUP%')
       OR (e.ticker = 'BLW' AND UPPER(r.bronze_security_name) LIKE '%BLACKROCK%LIMITED%DURATION%')
       OR (e.ticker = 'ELLO' AND UPPER(r.bronze_security_name) LIKE '%ELLOMAY%')
)
SELECT security_id, ticker, price_date, target_provider_symbol,
       target_period_date, target_filing_date, target_shares,
       sourced_shares, shares_as_of_date,
       publication_date AS source_publication_date,
       source_name, source_url, source_document_id, source_excerpt,
       close, original_cap, close * sourced_shares AS proposed_cap,
       current_split_multiplier, period_split_multiplier,
       price_research_eligible
FROM candidate
"""


def stage(con):
    con.execute(STAGE_SQL)
    rows = con.execute("""
        SELECT ticker, source_document_id, sourced_shares,
               COUNT(*) AS affected_days, MIN(price_date), MAX(price_date),
               COUNT(DISTINCT (target_provider_symbol, target_period_date,
                               target_filing_date, target_shares)) AS vendor_facts,
               MAX(original_cap) AS peak_original_cap,
               MAX(proposed_cap) AS peak_proposed_cap,
               COUNT(DISTINCT (current_split_multiplier,
                               period_split_multiplier)) AS split_bases,
               COUNT(*) FILTER (WHERE price_research_eligible)
                   AS research_eligible_days
        FROM material_share_correction_stage
        GROUP BY 1, 2, 3 ORDER BY 1
    """).fetchall()
    if [r[0] for r in rows] != ['BLW', 'ELLO', 'FRG'] or any(r[3] == 0 for r in rows):
        raise ValueError(f'Expected three nonempty dated source cohorts: {rows}')
    invalid = con.execute("""
        SELECT ticker, price_date FROM material_share_correction_stage
        WHERE target_provider_symbol IS NULL OR target_period_date IS NULL
           OR target_filing_date IS NULL OR target_shares IS NULL
           OR sourced_shares <= 0 OR close <= 0
           OR current_split_multiplier IS DISTINCT FROM period_split_multiplier
        LIMIT 1
    """).fetchone()
    if invalid:
        raise ValueError(f'Incomplete source/price/split basis: {invalid}')
    duplicates = con.execute("""
        SELECT security_id, price_date FROM material_share_correction_stage
        GROUP BY 1, 2 HAVING COUNT(*) <> 1 LIMIT 1
    """).fetchone()
    if duplicates:
        raise ValueError(f'Duplicate dated adjustment: {duplicates}')
    return rows


def apply(con):
    """Apply exactly the reviewed stage; a mismatch rolls back all changes."""
    conflict = con.execute("""
        SELECT s.ticker, s.price_date, b.source_document_id
        FROM material_share_correction_stage s
        JOIN bronze.eodhd_share_manual_adjustment b
          ON b.security_id = s.security_id AND b.price_date = s.price_date
        WHERE b.source_document_id <> s.source_document_id LIMIT 1
    """).fetchone()
    if conflict:
        raise ValueError(f'Existing Bronze adjustment conflicts: {conflict}')
    con.execute('BEGIN TRANSACTION')
    try:
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment
            WHERE source_document_id IN (?, ?, ?)
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
            FROM material_share_correction_stage
        """)
        build(con, manage_transaction=False)
        mismatch = con.execute("""
            SELECT s.ticker, s.price_date, c.selected_source,
                   c.selected_shares_candidate
            FROM material_share_correction_stage s
            LEFT JOIN silver.security_daily_market_cap_source_priority_candidate c
              ON c.security_id = s.security_id AND c.date = s.price_date
            WHERE c.security_id IS NULL OR c.selected_source <> 'manual_sourced'
               OR c.selected_shares_candidate <> s.sourced_shares
            LIMIT 1
        """).fetchone()
        if mismatch:
            raise ValueError(f'Silver selection did not match Bronze: {mismatch}')
        result = con.execute("""
            SELECT s.ticker, COUNT(*) AS selected_days,
                   MIN(c.date), MAX(c.date), MAX(c.market_cap_candidate)
            FROM material_share_correction_stage s
            JOIN silver.security_daily_market_cap_source_priority_candidate c
              ON c.security_id = s.security_id AND c.date = s.price_date
            GROUP BY s.ticker ORDER BY s.ticker
        """).fetchall()
        con.execute('COMMIT')
        return result
    except Exception:
        con.execute('ROLLBACK')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Apply the approved Bronze corrections and rebuild Silver')
    args = parser.parse_args()
    with connect(read_only=not args.apply) as con:
        print('ticker | source | shares | days | first | last | vendor facts | '
              'peak original | peak proposed | split bases | eligible days')
        for row in stage(con):
            print(*row, sep=' | ')
        if args.apply:
            print('Rebuilt selected days | first | last | peak cap')
            for row in apply(con):
                print(*row, sep=' | ')
            print('NEXT LARGEST EODHD CAPS — one dated peak per security')
            for row in top_eodhd_outliers(con, 20):
                print(*row, sep=' | ')
        else:
            print('Read-only stage. No Bronze or Silver rows changed.')


if __name__ == '__main__':
    main()
