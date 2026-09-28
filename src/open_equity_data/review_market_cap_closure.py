"""One read-only review of remaining large market caps and ELLO evidence.

Run after build_msci_daily_share_preference. This report does not approve a
share source, write Bronze evidence, or change selected Silver market caps.
"""

from open_equity_data.db import connect
from open_equity_data.stage_ello_share_correction import (
    PROXY_SHARES,
    SOURCE_URL,
    stage as stage_ello,
)


TOP_CAPS_SQL = """
WITH largest_issues AS (
    SELECT security_id, MAX(market_cap_candidate) AS peak_cap
    FROM silver.security_daily_market_cap_source_priority_candidate
    WHERE price_research_eligible AND market_cap_candidate > 0
    GROUP BY security_id
    ORDER BY peak_cap DESC LIMIT 30
), top_issues AS (
    SELECT c.*
    FROM largest_issues l
    JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = l.security_id
     AND c.market_cap_candidate = l.peak_cap
    WHERE c.price_research_eligible
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.security_id ORDER BY c.date
    ) = 1
), daily_totals AS (
    SELECT c.date, SUM(c.market_cap_candidate) AS total_cap
    FROM silver.security_daily_market_cap_source_priority_candidate c
    WHERE c.price_research_eligible AND c.market_cap_candidate > 0
      AND c.date IN (SELECT date FROM top_issues)
    GROUP BY c.date
), issue_baselines AS (
    SELECT c.security_id,
           MEDIAN(c.selected_shares_candidate) AS median_selected_shares,
           MIN(c.date) AS first_selected_date,
           MAX(c.date) AS last_selected_date
    FROM silver.security_daily_market_cap_source_priority_candidate c
    WHERE c.selected_shares_candidate > 0
      AND c.security_id IN (SELECT security_id FROM top_issues)
    GROUP BY c.security_id
)
SELECT p.ticker, p.date, p.security_id, r.bronze_security_name,
       ROUND(p.market_cap_candidate / 1e9, 3) AS cap_usd_bn,
       ROUND(1e4 * p.market_cap_candidate / d.total_cap, 2) AS weight_bps,
       p.selected_source, p.selected_shares_candidate,
       ROUND(p.selected_shares_candidate /
             NULLIF(b.median_selected_shares, 0), 3) AS ratio_to_issue_median,
       p.close, p.eodhd_filed_shares, p.eodhd_basis_status,
       p.current_split_multiplier, p.period_split_multiplier,
       p.shares_filing_date, p.shares_period_date, p.price_source,
       b.first_selected_date, b.last_selected_date
FROM top_issues p
JOIN daily_totals d USING (date)
JOIN issue_baselines b USING (security_id)
LEFT JOIN silver.security_ticker_reference_resolution r
  ON r.security_id = p.security_id AND r.ticker = p.ticker
ORDER BY p.market_cap_candidate DESC
"""

SOURCE_COUNTS_SQL = """
SELECT selected_source, COUNT(*) AS issue_days,
       COUNT(DISTINCT security_id) AS issues,
       MAX(market_cap_candidate) AS peak_cap
FROM silver.security_daily_market_cap_source_priority_candidate
WHERE price_research_eligible
GROUP BY selected_source ORDER BY selected_source
"""

ELLO_BY_SOURCE_SQL = """
SELECT selected_source, eodhd_filed_shares, eodhd_basis_status,
       current_split_multiplier, period_split_multiplier,
       MIN(date) AS first_date, MAX(date) AS last_date,
       COUNT(*) AS days, MAX(market_cap_candidate) AS peak_cap
FROM silver.security_daily_market_cap_source_priority_candidate
WHERE security_id = 5988 AND ticker = 'ELLO'
  AND date BETWEEN DATE '2011-06-01' AND DATE '2012-06-01'
GROUP BY ALL ORDER BY first_date
"""


def report(con):
    print('SELECTED SOURCE COVERAGE — RESEARCH ELIGIBLE')
    for row in con.execute(SOURCE_COUNTS_SQL).fetchall():
        print(*row, sep=' | ')

    print('\nELLO ISSUER ANNOUNCEMENT — EXPECTED POST-SPLIT SHARES')
    print(PROXY_SHARES, SOURCE_URL, sep=' | ')
    print('ELLO REVIEW — candidate days | first | last | original peak cap | '
          'proxy peak cap | min ratio | max ratio | EODHD facts | split bases')
    print(*stage_ello(con), sep=' | ')
    print('ELLO EXISTING SELECTION — source | raw shares | basis status | '
          'current split | period split | first | last | days | peak cap')
    for row in con.execute(ELLO_BY_SOURCE_SQL).fetchall():
        print(*row, sep=' | ')

    print('\nTOP 30 RESEARCH-ELIGIBLE PEAK MARKET CAPS')
    print('ticker | date | security_id | name | cap USD bn | weight bps | '
          'source | shares | ratio to issue median | close | raw EODHD shares | '
          'basis | current split | period split | filing | period | '
          'price source | first selected | last selected')
    for row in con.execute(TOP_CAPS_SQL).fetchall():
        print(*row, sep=' | ')
    print('Read-only review. Bronze and selected Silver were not changed.')


def main():
    with connect(read_only=True) as con:
        report(con)


if __name__ == '__main__':
    main()
