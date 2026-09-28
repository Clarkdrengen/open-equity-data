from datetime import date

import duckdb

from open_equity_data.audit_eodhd_share_jump_guard import (
    build, classify_observations, summary,
)


def observation(issue, filing, shares, *, factor=1.0, eligible=True, invalid=False):
    filing = date.fromisoformat(filing)
    return (issue, 'A', 'A.US', filing, filing, shares, filing,
            filing if eligible else None, shares if eligible else None,
            factor if eligible else None, invalid, 1, 1)


def test_forward_only_repeated_bad_filings_and_expiry():
    rows = [
        observation(1, '2020-01-01', 40_000_000),
        observation(1, '2020-04-01', 40_000_000_000),
        observation(1, '2020-07-01', 41_000_000_000),
        observation(1, '2021-02-01', 39_000_000_000),
        observation(1, '2021-03-01', 40_500_000),
    ]
    out = classify_observations(rows)
    assert [r['guard_status'] for r in out] == [
        'no_prior_eligible_observation', 'quarantined_100x_up',
        'quarantined_100x_up', 'quarantined_100x_up', 'accepted']
    assert out[3]['prior_accepted_filing_date'] == date(2020, 1, 1)


def test_split_boundary_and_ineligible_records_do_not_trigger_jump():
    rows = [observation(1, '2020-01-01', 40_000_000),
            observation(1, '2020-02-01', 40_000_000_000, eligible=False),
            observation(1, '2020-03-01', 400_000_000, factor=10.0),
            observation(1, '2020-04-01', 400_000_000_000, factor=10.0)]
    assert [r['guard_status'] for r in classify_observations(rows)] == [
        'no_prior_eligible_observation', 'not_eligible',
        'split_boundary_unchecked', 'quarantined_100x_up']


def test_read_only_candidate_impact_carries_only_365_days_and_leaves_source():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT 1 AS security_id, 'A' AS ticker, date,
               'A.US' AS eodhd_provider_symbol,
               filing AS shares_filing_date, filing AS shares_period_date,
               shares AS eodhd_filed_shares,
               shares AS eodhd_current_shares_candidate,
               FALSE AS eodhd_observation_invalidated,
               1.0 AS current_split_multiplier,
               'eodhd' AS selected_source,
               shares AS selected_shares_candidate,
               shares * 10 AS market_cap_candidate, 10.0 AS close
        FROM (VALUES
            (DATE '2020-01-01', DATE '2020-01-01', 40000000.0),
            (DATE '2020-04-01', DATE '2020-04-01', 40000000000.0),
            (DATE '2021-01-01', DATE '2020-04-01', 40000000000.0)
        ) v(date, filing, shares)
    """)
    build(con)
    impact = con.execute("""
        SELECT date, dry_run_shares FROM silver.eodhd_share_jump_guard_impact_candidate
        ORDER BY date
    """).fetchall()
    assert impact == [(date(2020, 4, 1), 40_000_000.0),
                      (date(2021, 1, 1), None)]
    assert con.execute("""
        SELECT COUNT(*) FROM silver.security_daily_market_cap_source_priority_candidate
        WHERE selected_source = 'eodhd' AND market_cap_candidate = 400000000000
    """).fetchone()[0] == 2
    assert summary(con)[1][:4] == (2, 1, 1, 1)
