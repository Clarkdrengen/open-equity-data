"""Preview a dated, source-backed ELLO correction without changing Bronze or Silver.

The June 2, 2011 issuer announcement expected approximately 10,777,850
ordinary shares after the June 9 one-for-ten reverse split. This is a proxy,
not a claim that every later trading date had precisely that share count.
"""

from open_equity_data.db import connect


SOURCE_URL = (
    'https://www.prnewswire.com/news-releases/'
    'ellomay-capital-announces-a-one-for-ten-reverse-split-123034353.html'
)
PROXY_SHARES = 10_777_850.0


def stage(con):
    return con.execute("""
        WITH candidate AS (
            SELECT c.date, c.security_id, c.ticker, c.close,
                   c.selected_source, c.selected_shares_candidate,
                   c.market_cap_candidate, c.eodhd_filed_shares,
                   c.shares_filing_date, c.shares_period_date,
                   c.eodhd_basis_status, c.current_split_multiplier,
                   c.period_split_multiplier,
                   c.price_source,
                   c.close * ? AS proposed_cap,
                   c.market_cap_candidate / NULLIF(c.close * ?, 0)
                       AS cap_ratio
            FROM silver.security_daily_market_cap_source_priority_candidate c
            JOIN silver.security_ticker_reference_resolution r
              ON r.security_id = c.security_id AND r.ticker = c.ticker
            WHERE c.security_id = 5988 AND c.ticker = 'ELLO'
              AND UPPER(r.bronze_security_name) LIKE '%ELLOMAY%'
              AND c.date >= DATE '2011-06-09'
              AND c.date <= DATE '2012-06-01'
              AND c.selected_source = 'eodhd'
              AND c.close > 0
              AND c.selected_shares_candidate >= 100 * ?
        )
        SELECT COUNT(*) AS candidate_days, MIN(date) AS first_date,
               MAX(date) AS last_date,
               MAX(market_cap_candidate) AS peak_original_cap,
               MAX(proposed_cap) AS peak_proxy_cap,
               MIN(cap_ratio) AS minimum_ratio,
               MAX(cap_ratio) AS maximum_ratio,
               COUNT(DISTINCT (eodhd_filed_shares, shares_filing_date,
                               shares_period_date)) AS distinct_eodhd_facts,
               COUNT(DISTINCT (current_split_multiplier,
                               period_split_multiplier)) AS split_bases
        FROM candidate
    """, [PROXY_SHARES] * 3).fetchone()


def main():
    with connect(read_only=True) as con:
        result = stage(con)
    print('ELLO source:', SOURCE_URL)
    print('Post-split shares expected in issuer announcement:', PROXY_SHARES)
    print('days | first | last | original peak cap | proxy peak cap | '
          'minimum ratio | maximum ratio | EODHD facts | split bases')
    print(*result, sep=' | ')
    print('Read-only candidate. No Bronze adjustment or Silver selection changed.')


if __name__ == '__main__':
    main()
