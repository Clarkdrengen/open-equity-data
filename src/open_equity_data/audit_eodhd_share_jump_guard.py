"""Forward-only 100x EODHD filing jump diagnostics and pre-guard impact.

The source-priority builder generates these tables from its unguarded
selection, then applies the approved guard in Silver. This command reports
the original-versus-guarded impact retained from that build.
"""

from __future__ import annotations

import argparse

import pandas as pd

from open_equity_data.db import connect


OBSERVATIONS = """
SELECT security_id, ticker, eodhd_provider_symbol, shares_period_date,
       shares_filing_date, eodhd_filed_shares,
       MIN(date) AS first_price_date,
       MIN(date) FILTER (WHERE eodhd_current_shares_candidate > 0)
           AS first_eligible_date,
       ARG_MIN(eodhd_current_shares_candidate, date) FILTER (
           WHERE eodhd_current_shares_candidate > 0) AS first_eligible_shares,
       ARG_MIN(current_split_multiplier, date) FILTER (
           WHERE eodhd_current_shares_candidate > 0) AS first_eligible_factor,
       BOOL_OR(eodhd_observation_invalidated) AS invalidated,
       COUNT(*) AS priced_days,
       COUNT(*) FILTER (WHERE selected_source = 'eodhd') AS selected_days
FROM silver.security_daily_market_cap_source_priority_candidate
WHERE eodhd_filed_shares > 0 AND shares_filing_date IS NOT NULL
  AND close > 0
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY security_id, shares_filing_date, shares_period_date,
         eodhd_provider_symbol, eodhd_filed_shares
"""


def classify_observations(rows, threshold=100.0):
    """Keep last accepted *eligible* observation; never learn from a flag.

    Split boundaries are left unclassified and accepted as a fresh baseline;
    this candidate does not infer share basis across corporate actions.
    """
    accepted = {}
    output = []
    for row in rows:
        (security_id, ticker, provider, period, filing, raw, first_date,
         eligible_date, shares, factor, invalidated, priced_days,
         selected_days) = row
        previous = accepted.get(security_id)
        ratio = None
        if invalidated or shares is None or factor is None or factor <= 0:
            status = 'not_eligible'
        elif previous is None:
            status = 'no_prior_eligible_observation'
        elif abs(float(factor) / previous['factor'] - 1) > 0.01:
            status = 'split_boundary_unchecked'
        else:
            ratio = float(shares) / previous['shares']
            status = 'quarantined_100x_up' if ratio >= threshold else 'accepted'

        output.append({
            'security_id': security_id, 'ticker': ticker,
            'eodhd_provider_symbol': provider,
            'shares_period_date': period, 'shares_filing_date': filing,
            'eodhd_filed_shares': raw, 'first_price_date': first_date,
            'first_eligible_date': eligible_date,
            'first_eligible_shares': shares, 'first_eligible_factor': factor,
            'priced_days': priced_days, 'selected_days': selected_days,
            'guard_status': status, 'ratio_to_last_accepted': ratio,
            'prior_accepted_filing_date': previous['filing'] if previous else None,
            'prior_accepted_shares': previous['shares'] if previous else None,
            'prior_accepted_factor': previous['factor'] if previous else None,
        })
        if status in ('accepted', 'no_prior_eligible_observation',
                      'split_boundary_unchecked'):
            accepted[security_id] = {
                'filing': filing, 'shares': float(shares), 'factor': float(factor)
            }
    return output


IMPACT_SQL = """
CREATE OR REPLACE TABLE silver.eodhd_share_jump_guard_impact_candidate AS
WITH affected AS (
    SELECT c.security_id, c.date, c.ticker, c.close,
           c.market_cap_candidate AS original_cap,
           c.selected_shares_candidate AS original_shares,
           g.shares_filing_date, g.eodhd_filed_shares,
           g.ratio_to_last_accepted, g.prior_accepted_filing_date,
           CASE WHEN date_diff('day', CAST(g.prior_accepted_filing_date AS DATE), c.date)
                         BETWEEN 0 AND 365
                     AND c.current_split_multiplier > 0
                     AND g.prior_accepted_factor > 0
                     AND ABS(c.current_split_multiplier /
                             g.prior_accepted_factor - 1) <= 0.01
                THEN g.prior_accepted_shares END AS dry_run_shares
    FROM silver.security_daily_market_cap_source_priority_candidate c
    JOIN silver.eodhd_share_jump_guard_observation_candidate g
      ON c.security_id = g.security_id
     AND c.ticker = g.ticker
     AND c.eodhd_provider_symbol = g.eodhd_provider_symbol
     AND c.shares_period_date = g.shares_period_date
     AND c.shares_filing_date = g.shares_filing_date
     AND c.eodhd_filed_shares = g.eodhd_filed_shares
    WHERE g.guard_status = 'quarantined_100x_up'
      AND c.selected_source = 'eodhd'
)
SELECT *, CASE WHEN dry_run_shares > 0 AND close > 0
               THEN dry_run_shares * close END AS dry_run_cap
FROM affected
"""


def build(con):
    rows = con.execute(OBSERVATIONS).fetchall()
    candidates = pd.DataFrame(classify_observations(rows))
    if candidates.empty:
        raise ValueError('No priced EODHD observations found; build the source-priority candidate first')
    con.register('_share_guard_rows', candidates)
    try:
        con.execute("""
            CREATE OR REPLACE TABLE silver.eodhd_share_jump_guard_observation_candidate
            AS SELECT * FROM _share_guard_rows
        """)
    finally:
        con.unregister('_share_guard_rows')
    con.execute(IMPACT_SQL)
    return len(candidates)


def summary(con, limit=20):
    totals = con.execute("""
        SELECT guard_status, COUNT(*) AS observations,
               COUNT(DISTINCT security_id) AS issues,
               SUM(selected_days) AS original_selected_days
        FROM silver.eodhd_share_jump_guard_observation_candidate
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    impact = con.execute("""
        SELECT COUNT(*) AS affected_selected_days,
               COUNT(DISTINCT security_id) AS affected_issues,
               COUNT(*) FILTER (WHERE dry_run_shares > 0) AS carried_days,
               COUNT(*) FILTER (WHERE dry_run_shares IS NULL) AS null_days,
               MAX(original_cap) AS max_original_cap,
               MAX(dry_run_cap) AS max_dry_run_cap
        FROM silver.eodhd_share_jump_guard_impact_candidate
    """).fetchone()
    cases = con.execute("""
        SELECT security_id, MIN(ticker) AS ticker,
               MIN(date) AS first_affected, MAX(date) AS last_affected,
               COUNT(*) AS selected_days,
               COUNT(*) FILTER (WHERE dry_run_shares > 0) AS carried_days,
               MAX(original_cap) AS peak_original_cap,
               MAX(dry_run_cap) AS peak_dry_run_cap,
               MAX(ratio_to_last_accepted) AS peak_jump
        FROM silver.eodhd_share_jump_guard_impact_candidate
        GROUP BY security_id ORDER BY peak_original_cap DESC LIMIT ?
    """, [limit]).fetchall()
    return totals, impact, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    with connect(read_only=True) as con:
        count = con.execute("""
            SELECT COUNT(*)
            FROM silver.eodhd_share_jump_guard_observation_candidate
        """).fetchone()[0]
        totals, impact, cases = summary(con, args.limit)
    print(f'Priced EODHD source observations: {count}')
    print('guard status | observations | issues | originally selected days')
    for row in totals:
        print(*row, sep=' | ')
    print('affected selected days | issues | carry within 365 days | null days | '
          'peak original cap | peak dry-run cap')
    print(*impact, sep=' | ')
    print('security_id | ticker | first | last | days | carried | '
          'peak original cap | peak dry-run cap | largest jump')
    for row in cases:
        print(*row, sep=' | ')
    print('The source-priority build applies this guard in Silver; impact rows '
          'retain pre-guard caps. First bad filings and split boundaries remain unchecked.')


if __name__ == '__main__':
    main()
