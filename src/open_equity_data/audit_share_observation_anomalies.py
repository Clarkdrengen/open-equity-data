"""Rank EODHD share-source records across the full priced universe.

The Silver audit is diagnostic and does not change selected shares or caps.
One source observation may affect hundreds of priced days. Run after building
silver.security_daily_market_cap_source_priority_candidate.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from open_equity_data.db import connect


SQL = (Path(__file__).resolve().parents[2]
       / "sql/silver/create_share_observation_anomaly_audit.sql")


def build(con):
    con.execute(SQL.read_text())


def summary(con):
    return con.execute("""
        SELECT review_reason, COUNT(*) AS observations,
               COUNT(DISTINCT security_id) AS issues,
               SUM(priced_days) AS priced_days,
               SUM(selected_days) AS selected_days,
               MAX(max_selected_cap) AS largest_selected_cap
        FROM silver.share_observation_anomaly_audit
        GROUP BY 1 ORDER BY CASE WHEN review_reason = 'no_flag' THEN 1 ELSE 0 END,
                         selected_days DESC
    """).fetchall()


def queue(con, limit: int, *, selected: bool):
    return con.execute("""
        SELECT a.security_id, a.ticker, a.eodhd_provider_symbol,
               a.shares_period_date, a.shares_filing_date,
               a.eodhd_filed_shares, a.share_basis_proxy,
               a.review_reason, ROUND(a.robust_z, 1),
               ROUND(EXP(a.adjacent_log_ratio), 2),
               ROUND(EXP(a.cross_source_log_ratio), 2),
               a.priced_days, a.selected_days,
               ROUND(a.max_selected_cap / 1000000000, 2),
               ROUND(a.max_raw_cap / 1000000000, 2),
               a.invalidated
        FROM silver.share_observation_anomaly_audit a
        WHERE a.review_reason <> 'no_flag'
          AND (a.selected_days > 0) = ?
        ORDER BY COALESCE(a.max_selected_cap, a.max_raw_cap) DESC,
                 a.security_id, a.shares_filing_date
        LIMIT ?
    """, [selected, limit]).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    with connect() as con:
        build(con)
        totals = summary(con)
        selected = queue(con, args.limit, selected=True)
        other = queue(con, args.limit, selected=False)
    print('reason | observations | issues | priced_days | selected_days | largest_selected_cap')
    for row in totals:
        print(*row, sep=' | ')
    header = ('security_id | ticker | provider | period | filing | raw_shares | '
              'split_adjusted_basis | reason | robust_z | adjacent_ratio | '
              'cross_source_ratio | priced_days | selected_days | '
              'max_selected_cap_bn | max_raw_cap_bn | already_invalidated')
    print('SELECTED ANOMALIES (ranked by maximum selected cap)')
    print(header)
    for row in selected:
        print(*row, sep=' | ')
    print('UNSELECTED SOURCE ANOMALIES (ranked by maximum raw cap)')
    print(header)
    for row in other:
        print(*row, sep=' | ')
    print('Diagnostic only: no Bronze source or Silver market cap was changed.')


if __name__ == '__main__':
    main()
