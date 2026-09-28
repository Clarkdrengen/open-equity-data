"""Preview SEC-backed Bronze adjustments for three high-impact cases.

Default is read-only. --apply writes dated Bronze rows and rebuilds Silver
after the proposed dates have been reviewed. Proposals are restricted to
selected EODHD days flagged by audit_eodhd_share_jump_guard and to filing
evidence available by that close.
"""

from __future__ import annotations

import argparse

from open_equity_data.build_msci_daily_share_preference import MANUAL_SCHEMA, build
from open_equity_data.db import connect


STAGE_SQL = """
CREATE OR REPLACE TEMP TABLE sec_share_jump_correction_preview AS
WITH sources AS (
    SELECT * FROM (VALUES
        (7462, 'FRST', DATE '2021-08-09', DATE '2021-08-09',
         DATE '2021-08-02', 24539369.0, '0001558370-21-010914',
         'https://www.sec.gov/Archives/edgar/data/1325670/000155837021010914/frst-20210630x10q.htm',
         '24,539,369 shares of common stock outstanding as of August 2, 2021',
         'PRIMIS'),
        (7462, 'FRST', DATE '2021-11-09', DATE '2021-11-09',
         DATE '2021-11-02', 24574619.0, '0001558370-21-015243',
         'https://www.sec.gov/Archives/edgar/data/1325670/000155837021015243/frst-20210930x10q.htm',
         '24,574,619 shares of common stock outstanding as of November 2, 2021',
         'PRIMIS'),
        (6487, 'EVBN', DATE '2012-11-02', DATE '2012-11-02',
         DATE '2012-10-30', 4157422.0, '0001193125-12-448401',
         'https://www.sec.gov/Archives/edgar/data/842518/000119312512448401/d431636d10q.htm',
         '4,157,422 shares of common stock outstanding as of October 30, 2012',
         'EVANS BANCORP'),
        -- This 10-K was accepted at 16:30 ET on March 4. It cannot set
        -- that day\'s closing share count; first eligible date is March 5.
        (6487, 'EVBN', DATE '2013-03-04', DATE '2013-03-05',
         DATE '2013-03-01', 4171473.0, '0001562762-13-000070',
         'https://www.sec.gov/Archives/edgar/data/842518/000156276213000070/evbn-20121231x10k.htm',
         '4,171,473 shares of common stock outstanding as of March 1, 2013',
         'EVANS BANCORP'),
        -- This filing was accepted at 16:31 ET on November 12, 2019.
        -- The count is the NYSE LHC Class A issue, not Class B founder shares.
        (11532, 'LHC', DATE '2019-11-12', DATE '2019-11-13',
         DATE '2019-11-12', 20000000.0, '0001193125-19-290000',
         'https://www.sec.gov/Archives/edgar/data/1725134/000119312519290000/d810303d10q.htm',
         '20,000,000 Class A ordinary shares outstanding as of November 12, 2019',
         'LEO HOLDINGS')
    ) AS v(security_id, ticker, source_publication_date,
           first_eligible_date, shares_as_of_date, sourced_shares,
           source_document_id, source_url, source_excerpt, name_check)
), proposed AS (
    SELECT i.security_id, i.ticker, i.date AS price_date,
           s.sourced_shares, s.shares_as_of_date,
           s.source_publication_date, s.first_eligible_date,
           'SEC 10-Q/10-K cover page' AS source_name, s.source_document_id,
           s.source_url, s.source_excerpt,
           c.eodhd_provider_symbol AS target_provider_symbol,
           c.shares_period_date AS target_period_date,
           c.shares_filing_date AS target_filing_date,
           c.eodhd_filed_shares AS target_shares,
           r.bronze_security_name,
           i.original_cap, i.close * s.sourced_shares AS proposed_cap
    FROM silver.eodhd_share_jump_guard_impact_candidate i
    JOIN sources s ON s.security_id = i.security_id AND s.ticker = i.ticker
      AND i.date >= s.first_eligible_date
      AND date_diff('day', s.source_publication_date, i.date) BETWEEN 0 AND 365
    JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = i.security_id AND c.date = i.date
     AND c.ticker = i.ticker AND c.selected_source = 'eodhd'
     AND c.shares_filing_date = i.shares_filing_date
     AND c.eodhd_filed_shares = i.eodhd_filed_shares
    JOIN silver.security_ticker_reference_resolution r
      ON r.security_id = i.security_id AND r.ticker = i.ticker
     AND UPPER(r.bronze_security_name) LIKE '%' || s.name_check || '%'
    WHERE c.eodhd_normalized_shares >= s.sourced_shares * 100
      AND NOT EXISTS (
          SELECT 1 FROM sources newer
          WHERE newer.security_id = s.security_id
            AND newer.source_publication_date > s.source_publication_date
            AND newer.first_eligible_date <= i.date
      )
)
SELECT * FROM proposed
"""


def stage(con):
    con.execute(STAGE_SQL)
    duplicate = con.execute("""
        SELECT security_id, price_date FROM sec_share_jump_correction_preview
        GROUP BY ALL HAVING COUNT(*) > 1 LIMIT 1
    """).fetchone()
    if duplicate:
        raise ValueError(f'Duplicate security/date proposal: {duplicate}')
    return con.execute("""
        SELECT ticker, source_document_id, sourced_shares, COUNT(*) AS days,
               MIN(price_date), MAX(price_date),
               MAX(original_cap), MAX(proposed_cap),
               COUNT(DISTINCT (target_provider_symbol, target_period_date,
                               target_filing_date, target_shares)) AS targeted_records
        FROM sec_share_jump_correction_preview
        GROUP BY 1, 2, 3 ORDER BY 1, 5
    """).fetchall()


def apply(con, rows):
    """Persist exact previewed rows in Bronze and rebuild Silver atomically."""
    ids = {row[1] for row in rows}
    expected = {'0001193125-12-448401', '0001562762-13-000070',
                '0001558370-21-010914', '0001558370-21-015243',
                '0001193125-19-290000'}
    if ids != expected or any(row[3] < 1 or row[8] != 1 for row in rows):
        raise ValueError(f'Incomplete or ambiguous SEC preview: {rows}')
    con.execute('BEGIN TRANSACTION')
    try:
        con.execute(MANUAL_SCHEMA.read_text())
        conflict = con.execute("""
            SELECT a.security_id, a.price_date, a.source_document_id
            FROM bronze.eodhd_share_manual_adjustment a
            JOIN sec_share_jump_correction_preview s
              ON a.security_id = s.security_id AND a.price_date = s.price_date
            WHERE a.source_document_id <> s.source_document_id
            LIMIT 1
        """).fetchone()
        if conflict:
            raise ValueError(f'Existing Bronze adjustment conflicts: {conflict}')
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment a
            USING sec_share_jump_correction_preview s
            WHERE a.security_id = s.security_id
              AND a.price_date = s.price_date
              AND a.source_document_id = s.source_document_id
        """)
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
            FROM sec_share_jump_correction_preview
        """)
        build(con, manage_transaction=False)
        mismatch = con.execute("""
            SELECT s.security_id, s.price_date,
                   c.selected_source, c.selected_shares_candidate,
                   s.sourced_shares
            FROM sec_share_jump_correction_preview s
            LEFT JOIN silver.security_daily_market_cap_source_priority_candidate c
              ON c.security_id = s.security_id AND c.date = s.price_date
            WHERE c.selected_source <> 'manual_sourced'
               OR ABS(c.selected_shares_candidate / s.sourced_shares - 1) > 0.001
               OR c.security_id IS NULL
            LIMIT 1
        """).fetchone()
        if mismatch:
            raise ValueError(f'Silver rebuild did not select sourced shares: {mismatch}')
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Write the previewed dates to Bronze and rebuild Silver')
    args = parser.parse_args()
    with connect(read_only=not args.apply) as con:
        rows = stage(con)
        if args.apply:
            apply(con, rows)
    print('ticker | SEC accession | sourced shares | affected days | '
          'first | last | peak original cap | peak proposed cap | target records')
    for row in rows:
        print(*row, sep=' | ')
    if args.apply:
        print('Applied exact dated adjustments to Bronze and rebuilt Silver.')
    else:
        print('Read-only Bronze adjustment preview; no source or selected cap changed.')


if __name__ == '__main__':
    main()
