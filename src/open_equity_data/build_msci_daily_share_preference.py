"""Build dated MSCI/EODHD daily shares and market-cap candidates.

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
        SELECT DISTINCT date FROM silver.security_daily_ohlcv_reconciled
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
        SELECT DISTINCT date FROM silver.security_daily_ohlcv_reconciled
    )
), base AS (
    SELECT px.security_id, px.date, px.ticker, c.session_number,
           o.shares_outstanding AS eodhd_filed_shares,
           o.shares_source AS eodhd_share_source,
           o.filing_date AS shares_filing_date,
           o.period_date AS shares_period_date,
           date_diff('day', o.filing_date, px.date) AS shares_age_days,
           COALESCE(i.ticker_identity_ambiguous, FALSE)
               AS ticker_identity_ambiguous,
           f.cumulative_split_multiplier AS current_split_multiplier,
           px.close, px.source AS price_source,
           px.research_eligible AS price_research_eligible
    FROM silver.security_daily_ohlcv_reconciled px
    JOIN calendar c ON c.date = px.date
    ASOF LEFT JOIN silver.security_shares_outstanding_effective o
      ON px.ticker = o.ticker AND px.date >= o.filing_date
    LEFT JOIN silver.shares_ticker_identity_diagnostic i
      ON i.ticker = px.ticker
    LEFT JOIN silver.security_daily_split_factor_reconciled f
      ON f.security_id = px.security_id AND f.date = px.date
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
           AND date_diff('day', msci_snapshot_date, date) BETWEEN 0 AND 365
           AND msci_anchor_price_date <= date
           AND current_split_multiplier > 0
           AND anchor_split_multiplier > 0
               AS msci_within_365_days,
           eodhd_filed_shares > 0
           AND shares_age_days BETWEEN 0 AND 365
           AND NOT COALESCE(ticker_identity_ambiguous, FALSE)
               AS eodhd_within_365_days
    FROM attached
)
SELECT security_id, date, ticker, family, msci_snapshot_date,
       msci_anchor_price_date, msci_security_code, isin,
       msci_snapshot_shares, eodhd_filed_shares,
       eodhd_share_source,
       shares_filing_date, shares_period_date, shares_age_days,
       close, price_source, price_research_eligible,
       msci_within_365_days, eodhd_within_365_days,
       CASE WHEN msci_within_365_days
            THEN msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier END AS msci_current_shares_candidate,
       CASE WHEN msci_within_365_days THEN 'msci'
            WHEN eodhd_within_365_days
                 THEN 'eodhd'
            ELSE 'no_eligible_share_source' END AS selected_source,
       CASE WHEN msci_within_365_days
            THEN msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier
            WHEN eodhd_within_365_days
            THEN eodhd_filed_shares END AS selected_shares_candidate,
       CASE WHEN close > 0 AND msci_within_365_days
            THEN close * msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier
            WHEN close > 0 AND eodhd_within_365_days
            THEN close * eodhd_filed_shares END AS market_cap_candidate
FROM classified
"""


def build(con):
    con.execute(SNAPSHOT_SQL)
    for lag in (1, 5, 22):
        con.execute(daily_sql(lag))
    return con.execute("""
        SELECT lag, selected_source, COUNT(*) AS issue_days,
               COUNT(DISTINCT security_id) AS issues,
               COUNT(*) FILTER (WHERE market_cap_candidate > 0)
                   AS priced_issue_days,
               MAX(market_cap_candidate) AS largest_cap_candidate
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
    print("lag_sessions | selected_source | issue_days | issues | priced_issue_days | largest_cap_candidate")
    for row in rows:
        print(*row, sep=" | ")
    print("Candidate only: MSCI release timing and third-priority source require review.")


if __name__ == "__main__":
    main()
