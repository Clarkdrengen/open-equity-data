from datetime import date

import duckdb

from open_equity_data.audit_eodhd_share_jump_guard import build
from open_equity_data.review_eodhd_share_jump_cases import (
    FILINGS_SQL, ISSUES_SQL, disposition, fetch_dicts,
)


def test_batch_report_sql_and_evidence_categories():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_source_priority_candidate AS
        SELECT 1 AS security_id, 'A' AS ticker, date,
               'A.US' AS eodhd_provider_symbol,
               filing AS shares_filing_date, filing AS shares_period_date,
               shares AS eodhd_filed_shares,
               shares AS eodhd_normalized_shares,
               shares AS eodhd_current_shares_candidate,
               NULL::DOUBLE AS msci_current_shares_candidate,
               NULL::DOUBLE AS manual_current_shares_candidate,
               FALSE AS eodhd_observation_invalidated,
               1.0 AS current_split_multiplier,
               'eodhd' AS selected_source,
               shares AS selected_shares_candidate,
               shares * 10 AS market_cap_candidate, 10.0 AS close
        FROM (VALUES
            (DATE '2020-01-01', DATE '2020-01-01', 40000000.0),
            (DATE '2020-04-01', DATE '2020-04-01', 40000000000.0),
            (DATE '2020-07-01', DATE '2020-07-01', 40000000.0)
        ) v(date, filing, shares)
    """)
    build(con)
    issues = fetch_dicts(con, ISSUES_SQL)
    filings = fetch_dicts(con, FILINGS_SQL)
    assert len(issues) == len(filings) == 1
    assert issues[0]['selected_days'] == 1
    assert issues[0]['first_near_prior_after_flag'] == date(2020, 7, 1)
    assert disposition(issues[0]) == 'later_eodhd_near_prior'
    assert filings[0]['peak_original_cap'] == 400_000_000_000


def test_prior_tiny_count_is_review_only():
    base = dict(msci_matches_prior_days=0, manual_matches_prior_days=0,
                msci_matches_new_days=0, manual_matches_new_days=0,
                first_near_prior_after_flag=None, median_carried_cap=66.0)
    assert disposition(base) == 'tiny_prior_cap_review'
    assert disposition({**base, 'msci_matches_new_days': 3}) == 'independent_supports_new'
