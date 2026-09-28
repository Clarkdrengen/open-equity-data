"""Review every 100x share jump in one local batch.

Uses the existing dry-run guard tables and writes one issue-level and one
filing-level CSV to Downloads. Only compact issue-level results are printed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from open_equity_data.db import connect


ISSUES_SQL = """
WITH flagged AS (
    SELECT security_id, MIN(ticker) AS ticker,
           COUNT(*) AS flagged_filings,
           MIN(shares_filing_date) AS first_flagged_filing,
           MAX(shares_filing_date) AS last_flagged_filing,
           MAX(ratio_to_last_accepted) AS largest_jump,
           ARG_MIN(prior_accepted_filing_date, shares_filing_date)
               AS first_prior_filing,
           ARG_MIN(prior_accepted_shares, shares_filing_date)
               AS first_prior_shares,
           ARG_MIN(prior_accepted_factor, shares_filing_date)
               AS first_prior_factor,
           ARG_MIN(first_eligible_shares, shares_filing_date)
               AS first_flagged_shares
    FROM silver.eodhd_share_jump_guard_observation_candidate
    WHERE guard_status = 'quarantined_100x_up'
      AND selected_days > 0
    GROUP BY security_id
), impact AS (
    SELECT security_id, COUNT(*) AS selected_days,
           COUNT(*) FILTER (WHERE dry_run_shares > 0) AS carried_days,
           COUNT(*) FILTER (WHERE dry_run_shares IS NULL) AS uncovered_days,
           MIN(date) AS first_selected_day, MAX(date) AS last_selected_day,
           MAX(original_cap) AS peak_original_cap,
           MAX(dry_run_cap) AS peak_carried_cap,
           MIN(dry_run_cap) AS minimum_carried_cap,
           MEDIAN(dry_run_cap) AS median_carried_cap
    FROM silver.eodhd_share_jump_guard_impact_candidate
    GROUP BY security_id
), independent AS (
    SELECT g.security_id,
           COUNT(*) FILTER (WHERE c.msci_current_shares_candidate > 0
             AND c.eodhd_normalized_shares > 0) AS msci_overlap_days,
           COUNT(*) FILTER (WHERE c.manual_current_shares_candidate > 0
             AND c.eodhd_normalized_shares > 0) AS manual_overlap_days,
           COUNT(*) FILTER (WHERE c.msci_current_shares_candidate > 0
             AND c.eodhd_normalized_shares > 0
             AND c.eodhd_normalized_shares /
                 c.msci_current_shares_candidate BETWEEN 0.5 AND 2)
             AS msci_matches_new_days,
           COUNT(*) FILTER (WHERE c.msci_current_shares_candidate > 0
             AND c.current_split_multiplier > 0
             AND ABS(c.current_split_multiplier /
                     g.prior_accepted_factor - 1) <= 0.01
             AND g.prior_accepted_shares /
                 c.msci_current_shares_candidate BETWEEN 0.5 AND 2)
             AS msci_matches_prior_days,
           COUNT(*) FILTER (WHERE c.manual_current_shares_candidate > 0
             AND c.eodhd_normalized_shares > 0
             AND c.eodhd_normalized_shares /
                 c.manual_current_shares_candidate BETWEEN 0.5 AND 2)
             AS manual_matches_new_days,
           COUNT(*) FILTER (WHERE c.manual_current_shares_candidate > 0
             AND c.current_split_multiplier > 0
             AND ABS(c.current_split_multiplier /
                     g.prior_accepted_factor - 1) <= 0.01
             AND g.prior_accepted_shares /
                 c.manual_current_shares_candidate BETWEEN 0.5 AND 2)
             AS manual_matches_prior_days
    FROM silver.eodhd_share_jump_guard_observation_candidate g
    JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = g.security_id AND c.ticker = g.ticker
     AND c.eodhd_provider_symbol = g.eodhd_provider_symbol
     AND c.shares_filing_date = g.shares_filing_date
     AND c.shares_period_date = g.shares_period_date
     AND c.eodhd_filed_shares = g.eodhd_filed_shares
    WHERE g.guard_status = 'quarantined_100x_up'
      AND g.selected_days > 0
    GROUP BY g.security_id
), later AS (
    SELECT f.security_id,
           MIN(g.shares_filing_date) FILTER (
             WHERE g.guard_status IN ('accepted', 'split_boundary_unchecked')
               AND g.first_eligible_factor > 0
               AND ABS(g.first_eligible_factor /
                       f.first_prior_factor - 1) <= 0.01
               AND g.first_eligible_shares / f.first_prior_shares
                   BETWEEN 0.5 AND 2) AS first_near_prior_after_flag
    FROM flagged f
    JOIN silver.eodhd_share_jump_guard_observation_candidate g
      ON g.security_id = f.security_id
     AND g.shares_filing_date > f.first_flagged_filing
    GROUP BY f.security_id, f.first_prior_shares, f.first_prior_factor
), selected_daily_totals AS (
    SELECT date,
           SUM(market_cap_candidate) FILTER (
               WHERE price_research_eligible AND market_cap_candidate > 0)
               AS selected_research_total_cap
    FROM silver.security_daily_market_cap_source_priority_candidate
    WHERE date IN (
        SELECT DISTINCT date
        FROM silver.eodhd_share_jump_guard_impact_candidate
    )
    GROUP BY date
), original_daily_totals AS (
    SELECT d.date,
           d.selected_research_total_cap + COALESCE(SUM(
               CASE WHEN c.price_research_eligible
                         AND c.selected_source <> 'eodhd'
                    THEN i.original_cap - COALESCE(i.dry_run_cap, 0)
                    ELSE 0 END), 0) AS research_total_cap
    FROM selected_daily_totals d
    LEFT JOIN silver.eodhd_share_jump_guard_impact_candidate i
      ON i.date = d.date
    LEFT JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = i.security_id AND c.date = i.date
    GROUP BY d.date, d.selected_research_total_cap
), materiality AS (
    SELECT i.security_id,
           COUNT(*) FILTER (WHERE c.price_research_eligible)
               AS research_eligible_days,
           MAX(10000.0 * i.original_cap / d.research_total_cap)
               FILTER (WHERE c.price_research_eligible
                         AND d.research_total_cap > 0)
               AS peak_reported_weight_bps,
           MAX(10000.0 * GREATEST(i.original_cap - i.dry_run_cap, 0)
               / d.research_total_cap)
               FILTER (WHERE c.price_research_eligible
                         AND d.research_total_cap > 0
                         AND i.dry_run_cap IS NOT NULL)
               AS peak_carry_delta_bps
    FROM silver.eodhd_share_jump_guard_impact_candidate i
    JOIN silver.security_daily_market_cap_source_priority_candidate c
      ON c.security_id = i.security_id AND c.ticker = i.ticker
     AND c.date = i.date
    LEFT JOIN original_daily_totals d ON d.date = i.date
    GROUP BY i.security_id
)
SELECT f.*, i.selected_days, i.carried_days, i.uncovered_days,
       i.first_selected_day, i.last_selected_day,
       i.peak_original_cap, i.peak_carried_cap,
       i.minimum_carried_cap, i.median_carried_cap,
       d.msci_overlap_days, d.manual_overlap_days,
       d.msci_matches_new_days, d.msci_matches_prior_days,
       d.manual_matches_new_days, d.manual_matches_prior_days,
       l.first_near_prior_after_flag,
       m.research_eligible_days, m.peak_reported_weight_bps,
       m.peak_carry_delta_bps
FROM flagged f
JOIN impact i USING (security_id)
LEFT JOIN independent d USING (security_id)
LEFT JOIN later l USING (security_id)
LEFT JOIN materiality m USING (security_id)
ORDER BY m.peak_reported_weight_bps DESC NULLS LAST, f.security_id
"""


FILINGS_SQL = """
SELECT g.security_id, g.ticker, g.eodhd_provider_symbol,
       g.shares_period_date, g.shares_filing_date,
       g.eodhd_filed_shares, g.first_eligible_shares,
       g.prior_accepted_filing_date, g.prior_accepted_shares,
       g.ratio_to_last_accepted, g.selected_days,
       MIN(i.date) AS first_selected_day, MAX(i.date) AS last_selected_day,
       COUNT(i.date) AS selected_days_in_impact,
       COUNT(i.dry_run_shares) AS carried_days,
       MAX(i.original_cap) AS peak_original_cap,
       MAX(i.dry_run_cap) AS peak_carried_cap
FROM silver.eodhd_share_jump_guard_observation_candidate g
LEFT JOIN silver.eodhd_share_jump_guard_impact_candidate i
  ON i.security_id = g.security_id AND i.ticker = g.ticker
 AND i.shares_filing_date = g.shares_filing_date
 AND i.eodhd_filed_shares = g.eodhd_filed_shares
WHERE g.guard_status = 'quarantined_100x_up'
  AND g.selected_days > 0
GROUP BY ALL
ORDER BY peak_original_cap DESC NULLS LAST, g.security_id,
         g.shares_filing_date
"""


def disposition(row):
    """Evidence category, not an approved source correction."""
    d = row
    prior = d['msci_matches_prior_days'] + d['manual_matches_prior_days']
    new = d['msci_matches_new_days'] + d['manual_matches_new_days']
    if prior > 0 and new == 0:
        return 'independent_supports_prior'
    if new > 0 and prior == 0:
        return 'independent_supports_new'
    if prior > 0 and new > 0:
        return 'conflicting_independent_evidence'
    if d['first_near_prior_after_flag'] is not None:
        return 'later_eodhd_near_prior'
    if d['median_carried_cap'] is not None and d['median_carried_cap'] < 1_000_000:
        return 'tiny_prior_cap_review'
    return 'unresolved'


def fetch_dicts(con, sql):
    result = con.execute(sql)
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path.home() / 'Downloads')
    parser.add_argument('--min-peak-bps', type=float, default=1.0,
                        help='Only print issues above this reported daily '
                             'research-universe weight; CSV retains all')
    args = parser.parse_args()
    if args.min_peak_bps < 0:
        parser.error('--min-peak-bps must be nonnegative')
    with connect(read_only=True) as con:
        issues = fetch_dicts(con, ISSUES_SQL)
        filings = fetch_dicts(con, FILINGS_SQL)
    if not issues:
        raise ValueError('No selected 100x cases: run audit_eodhd_share_jump_guard first')
    for row in issues:
        row['evidence_category'] = disposition(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    issue_path = args.output_dir / f'share_jump_review_issues_{stamp}.csv'
    filing_path = args.output_dir / f'share_jump_review_filings_{stamp}.csv'
    write_csv(issue_path, issues)
    write_csv(filing_path, filings)
    counts = {}
    for row in issues:
        category = row['evidence_category']
        counts[category] = counts.get(category, 0) + 1
    print(f'Reviewed {len(issues)} securities, {len(filings)} selected flagged filings')
    print('Evidence categories:', counts)
    material = [r for r in issues if r['peak_reported_weight_bps'] is not None
                and r['peak_reported_weight_bps'] >= args.min_peak_bps]
    print(f'{len(material)} securities reached at least {args.min_peak_bps:g} '
          'basis points of the recorded research-universe cap on a flagged date')
    print('ticker | peak_reported_weight_bps | peak_carry_delta_bps | '
          'research_eligible_days | category | original_peak_bn | median_carried_cap_m | '
          'selected_days | uncovered_days | independent_overlap_days | '
          'first_near_prior_after_flag')
    for row in material:
        print(row['ticker'], round(row['peak_reported_weight_bps'], 2),
              round(row['peak_carry_delta_bps'], 2)
                  if row['peak_carry_delta_bps'] is not None else None,
              row['research_eligible_days'], row['evidence_category'],
              round(row['peak_original_cap'] / 1e9, 3),
              round(row['median_carried_cap'] / 1e6, 3)
                  if row['median_carried_cap'] is not None else None,
              row['selected_days'], row['uncovered_days'],
              row['msci_overlap_days'] + row['manual_overlap_days'],
              row['first_near_prior_after_flag'], sep=' | ')
    print(f'Issue-level CSV: {issue_path}')
    print(f'Filing-level CSV: {filing_path}')
    print('Evidence categories are diagnostic. The source-priority build '
          'already applied the guard in Silver; this read-only report retains '
          'the pre-guard selected days and weights. A null carry does not '
          'establish the true correction.')


if __name__ == '__main__':
    main()
