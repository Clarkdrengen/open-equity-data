"""Preview dated SEC-backed Bronze adjustments for three high-impact cases.

Read only. No Bronze rows are inserted and selected Silver remains unchanged.
The proposed dates are restricted to selected EODHD days already flagged by
audit_eodhd_share_jump_guard and to filing evidence available by that close.
"""

from __future__ import annotations

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


def main():
    with connect(read_only=True) as con:
        rows = stage(con)
    print('ticker | SEC accession | sourced shares | affected days | '
          'first | last | peak original cap | peak proposed cap | target records')
    for row in rows:
        print(*row, sep=' | ')
    print('Read-only Bronze adjustment preview; no source or selected cap changed.')


if __name__ == '__main__':
    main()
