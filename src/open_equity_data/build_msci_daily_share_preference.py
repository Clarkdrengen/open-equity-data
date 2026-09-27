"""Build a reversible daily MSCI-first share candidate with availability lags.

This is a source-priority sensitivity, not a PIT release-date assertion or a
canonical market-cap replacement.
"""

from __future__ import annotations

from open_equity_data.db import connect


SNAPSHOT_SQL = """
CREATE OR REPLACE TABLE silver.msci_preferred_share_snapshot_candidate AS
WITH all_sources AS (
    SELECT 'm15d' AS family, security_id, ticker, observation_date,
           price_date, msci_security_code, isin, rif_closing_shares,
           closing_share_variants, project_security_matches, identity_status
    FROM silver.msci_m15d_rif_share_overlap_audit
    UNION ALL
    SELECT 'm15e' AS family, security_id, ticker, observation_date,
           price_date, msci_security_code, isin, rif_closing_shares,
           closing_share_variants, project_security_matches, identity_status
    FROM silver.msci_m15e_rif_share_overlap_audit
), unique_source AS (
    SELECT *, COUNT(*) OVER (
        PARTITION BY security_id, observation_date
    ) AS same_issue_snapshot_rows
    FROM all_sources
), calendar AS (
    SELECT date, ROW_NUMBER() OVER (ORDER BY date) AS session_number
    FROM (
        SELECT DISTINCT date FROM silver.research_universe_eligibility
        WHERE primary_research_eligible_exchange
    )
), first_after AS (
    SELECT s.observation_date, MIN(c.session_number) AS first_session
    FROM (SELECT DISTINCT observation_date FROM unique_source) s
    JOIN calendar c ON c.date > s.observation_date
    GROUP BY 1
)
SELECT s.*, f.cumulative_split_multiplier AS anchor_split_multiplier,
       a.first_session AS effective_session_1,
       a.first_session + 4 AS effective_session_5,
       a.first_session + 21 AS effective_session_22
FROM unique_source s
LEFT JOIN silver.security_daily_split_factor_reconciled f
  ON f.security_id = s.security_id AND f.date = s.price_date
LEFT JOIN first_after a USING (observation_date)
WHERE s.identity_status = 'candidate_exact_code_name'
  AND s.project_security_matches = 1
  AND s.closing_share_variants = 1
  AND s.rif_closing_shares > 0
  AND s.same_issue_snapshot_rows = 1
"""


def daily_sql(lag: int) -> str:
    if lag not in (1, 5, 22):
        raise ValueError("Unsupported availability sensitivity")
    effective = f"effective_session_{lag}"
    return f"""
CREATE OR REPLACE TABLE silver.msci_daily_share_preference_lag{lag}_candidate AS
WITH calendar AS (
    SELECT date, ROW_NUMBER() OVER (ORDER BY date) AS session_number
    FROM (
        SELECT DISTINCT date FROM silver.research_universe_eligibility
        WHERE primary_research_eligible_exchange
    )
), base AS (
    SELECT u.security_id, u.date, u.ticker, c.session_number,
           p.shares_outstanding AS eodhd_filed_shares,
           p.shares_filing_date, p.shares_period_date, p.shares_age_days,
           p.shares_pit_available, p.ticker_identity_ambiguous,
           (mi.security_id IS NOT NULL) AS multi_issue_candidate,
           f.cumulative_split_multiplier AS current_split_multiplier,
           px.close, px.research_eligible AS price_research_eligible
    FROM silver.research_universe_eligibility u
    JOIN (SELECT DISTINCT security_id
          FROM silver.msci_preferred_share_snapshot_candidate) m USING (security_id)
    JOIN calendar c ON c.date = u.date
    JOIN silver.security_daily_shares_outstanding_pit p
      ON p.security_id = u.security_id
     AND p.date = u.date AND p.ticker = u.ticker
    LEFT JOIN silver.security_daily_split_factor_reconciled f
      ON f.security_id = u.security_id AND f.date = u.date
    LEFT JOIN silver.security_daily_ohlcv_reconciled px
      ON px.security_id = u.security_id AND px.date = u.date
    LEFT JOIN (
        SELECT security_id_a AS security_id
        FROM silver.multi_listed_common_equity_candidate
        UNION SELECT security_id_b AS security_id
        FROM silver.multi_listed_common_equity_candidate
    ) mi ON mi.security_id = u.security_id
    WHERE u.primary_research_eligible_exchange
), attached AS (
    SELECT b.*, s.family, s.observation_date AS msci_snapshot_date,
           s.price_date AS msci_anchor_price_date,
           s.msci_security_code, s.isin,
           s.rif_closing_shares AS msci_snapshot_shares,
           s.anchor_split_multiplier
    FROM base b
    ASOF LEFT JOIN silver.msci_preferred_share_snapshot_candidate s
      ON b.security_id = s.security_id
     AND b.session_number >= s.{effective}
), classified AS (
    SELECT *,
           msci_snapshot_date IS NOT NULL
           AND date_diff('day', msci_snapshot_date, date) BETWEEN 0 AND 45
           AND current_split_multiplier > 0
           AND anchor_split_multiplier > 0
               AS msci_fresh_and_split_supported,
           COALESCE(shares_pit_available, FALSE)
           AND eodhd_filed_shares > 0
           AND NOT COALESCE(ticker_identity_ambiguous, FALSE)
               AS eodhd_record_available
    FROM attached
)
SELECT security_id, date, ticker, family, msci_snapshot_date,
       msci_anchor_price_date, msci_security_code, isin,
       msci_snapshot_shares, eodhd_filed_shares,
       shares_filing_date, shares_period_date, shares_age_days,
       close, price_research_eligible,
       msci_fresh_and_split_supported, eodhd_record_available,
       multi_issue_candidate,
       CASE WHEN msci_fresh_and_split_supported AND eodhd_record_available
            THEN msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier END AS msci_current_shares_candidate,
       CASE WHEN msci_fresh_and_split_supported AND eodhd_record_available
                  AND close > 0 AND price_research_eligible
            THEN close * msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier END AS msci_market_cap_candidate,
       CASE WHEN msci_fresh_and_split_supported AND eodhd_record_available
            THEN 'msci_preferred_where_both'
            WHEN eodhd_record_available AND NOT multi_issue_candidate
                 THEN 'eodhd_only_or_msci_not_yet_available'
            WHEN multi_issue_candidate THEN 'multi_issue_without_usable_msci'
            WHEN msci_fresh_and_split_supported THEN 'msci_only_pending_policy'
            ELSE 'neither_source_eligible' END AS source_status
FROM classified
"""


def build(con):
    con.execute(SNAPSHOT_SQL)
    for lag in (1, 5, 22):
        con.execute(daily_sql(lag))
    return con.execute("""
        SELECT lag, source_status, COUNT(*) AS issue_days,
               COUNT(DISTINCT security_id) AS issues,
               COUNT(*) FILTER (WHERE close > 0 AND price_research_eligible
                                     AND msci_current_shares_candidate > 0)
                   AS priced_msci_issue_days,
               MAX(msci_market_cap_candidate) AS largest_msci_cap_candidate
        FROM (
            SELECT 1 AS lag, * FROM silver.msci_daily_share_preference_lag1_candidate
            UNION ALL
            SELECT 5 AS lag, * FROM silver.msci_daily_share_preference_lag5_candidate
            UNION ALL
            SELECT 22 AS lag, * FROM silver.msci_daily_share_preference_lag22_candidate
        )
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()


def main():
    with connect() as con:
        rows = build(con)
    print("lag_sessions | status | issue_days | issues | priced_msci_issue_days | largest_msci_cap_candidate")
    for row in rows:
        print(*row, sep=" | ")
    print("Candidate only: MSCI source release timing and daily cap adoption are unapproved.")


if __name__ == "__main__":
    main()
