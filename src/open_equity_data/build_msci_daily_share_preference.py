"""Build dated MSCI/EODHD daily shares and market-cap candidates.

MSCI observations represent the close at the end of their calculation month.
This is a source-priority candidate, not a canonical market-cap replacement.
"""

from __future__ import annotations

from pathlib import Path

from open_equity_data.db import connect


MANUAL_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "sql/bronze/create_eodhd_share_manual_adjustment.sql"
)


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
)
SELECT s.*, f.cumulative_split_multiplier AS anchor_split_multiplier
FROM unique_source s
LEFT JOIN silver.security_daily_split_factor_reconciled f
  ON f.security_id = s.security_id AND f.date = s.price_date
WHERE s.identity_status = 'candidate_exact_code_name'
  AND s.project_security_matches = 1
  AND s.closing_share_variants = 1
  AND s.rif_closing_shares > 0
  AND s.same_issue_snapshot_rows = 1
"""


DAILY_SQL = """
CREATE OR REPLACE TABLE silver.security_daily_market_cap_source_priority_candidate AS
WITH base AS (
    SELECT px.security_id, px.date, px.ticker,
           o.shares_outstanding AS eodhd_filed_shares,
           o.provider_symbol AS eodhd_provider_symbol,
           o.shares_source AS eodhd_share_source,
           o.filing_date AS shares_filing_date,
           o.period_date AS shares_period_date,
           date_diff('day', o.filing_date, px.date) AS shares_age_days,
           COALESCE(i.ticker_identity_ambiguous, FALSE)
               AS ticker_identity_ambiguous,
           f.cumulative_split_multiplier AS current_split_multiplier,
           m.sourced_shares AS manual_shares,
           m.shares_as_of_date AS manual_as_of_date,
           m.source_publication_date AS manual_publication_date,
           m.source_name AS manual_source_name,
           m.source_url AS manual_source_url,
           m.source_document_id AS manual_document_id,
           (bad.security_id IS NOT NULL) AS eodhd_observation_invalidated,
           px.close, px.source AS price_source,
           px.research_eligible AS price_research_eligible
    FROM silver.security_daily_ohlcv_reconciled px
    ASOF LEFT JOIN silver.security_shares_outstanding_effective o
      ON px.ticker = o.ticker AND px.date >= o.filing_date
    ASOF LEFT JOIN bronze.eodhd_share_manual_adjustment m
      ON px.security_id = m.security_id AND px.ticker = m.ticker
     AND px.date >= m.source_publication_date
    LEFT JOIN bronze.eodhd_share_manual_adjustment bad
      ON bad.security_id = px.security_id
     AND bad.ticker = px.ticker
     AND bad.target_provider_symbol = o.provider_symbol
     AND bad.target_period_date = o.period_date
     AND bad.target_filing_date = o.filing_date
     AND bad.target_shares = o.shares_outstanding
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
     AND b.date >= s.observation_date
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
               AS eodhd_within_365_days,
           manual_shares > 0
           AND date_diff('day', manual_publication_date, date) BETWEEN 0 AND 365
               AS manual_within_365_days
    FROM attached
)
SELECT security_id, date, ticker, family, msci_snapshot_date,
       msci_anchor_price_date, msci_security_code, isin,
       msci_snapshot_shares, eodhd_filed_shares, eodhd_provider_symbol,
       eodhd_share_source,
       manual_shares, manual_as_of_date,
       manual_publication_date, manual_source_name,
       manual_source_url, manual_document_id,
       eodhd_observation_invalidated,
       shares_filing_date, shares_period_date, shares_age_days,
       close, price_source, price_research_eligible,
       msci_within_365_days, eodhd_within_365_days,
       manual_within_365_days,
       CASE WHEN msci_within_365_days
            THEN msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier END AS msci_current_shares_candidate,
       CASE WHEN msci_within_365_days THEN 'msci'
            WHEN manual_within_365_days THEN 'manual_sourced'
            WHEN eodhd_within_365_days
                 AND NOT eodhd_observation_invalidated
                 THEN 'eodhd'
            ELSE 'no_eligible_share_source' END AS selected_source,
       CASE WHEN msci_within_365_days
            THEN msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier
            WHEN manual_within_365_days THEN manual_shares
            WHEN eodhd_within_365_days
                 AND NOT eodhd_observation_invalidated
            THEN eodhd_filed_shares
            END AS selected_shares_candidate,
       CASE WHEN close > 0 AND msci_within_365_days
            THEN close * msci_snapshot_shares * current_split_multiplier
                 / anchor_split_multiplier
            WHEN close > 0 AND manual_within_365_days
            THEN close * manual_shares
            WHEN close > 0 AND eodhd_within_365_days
                 AND NOT eodhd_observation_invalidated
            THEN close * eodhd_filed_shares
            END AS market_cap_candidate
FROM classified
"""


def build(con):
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(MANUAL_SCHEMA.read_text())
        duplicate = con.execute("""
            SELECT security_id, ticker, target_provider_symbol,
                   target_period_date, target_filing_date, target_shares
            FROM bronze.eodhd_share_manual_adjustment
            WHERE target_provider_symbol IS NOT NULL
            GROUP BY ALL HAVING COUNT(*) > 1 LIMIT 1
        """).fetchone()
        if duplicate:
            raise ValueError(f"Duplicate manual share invalidation target: {duplicate}")
        duplicate_date = con.execute("""
            SELECT security_id, ticker, source_publication_date
            FROM bronze.eodhd_share_manual_adjustment
            GROUP BY ALL HAVING COUNT(*) > 1 LIMIT 1
        """).fetchone()
        if duplicate_date:
            raise ValueError(f"Ambiguous manual share date: {duplicate_date}")
        con.execute(SNAPSHOT_SQL)
        con.execute(DAILY_SQL)
        for lag in (1, 5, 22):
            con.execute(f"DROP TABLE IF EXISTS silver.msci_daily_share_preference_lag{lag}_candidate")
        rows = con.execute("""
        SELECT selected_source, COUNT(*) AS issue_days,
               COUNT(DISTINCT security_id) AS issues,
               COUNT(*) FILTER (WHERE market_cap_candidate > 0)
                   AS priced_issue_days,
               MAX(market_cap_candidate) AS largest_cap_candidate
        FROM silver.security_daily_market_cap_source_priority_candidate
        GROUP BY 1 ORDER BY 1
        """).fetchall()
        con.execute("COMMIT")
        return rows
    except Exception:
        con.execute("ROLLBACK")
        raise


def top_eodhd_outliers(con, limit: int = 12):
    """One peak dated observation per issue; no remediation is applied."""
    return con.execute("""
        WITH top_issues AS (
            SELECT security_id, MAX(market_cap_candidate) AS peak_cap
            FROM silver.security_daily_market_cap_source_priority_candidate
            WHERE selected_source = 'eodhd' AND market_cap_candidate > 0
            GROUP BY security_id
            ORDER BY peak_cap DESC
            LIMIT ?
        ), peaks AS (
            SELECT c.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.security_id ORDER BY c.date
                   ) AS rn
            FROM top_issues t
            JOIN silver.security_daily_market_cap_source_priority_candidate c
              ON c.security_id = t.security_id
             AND c.market_cap_candidate = t.peak_cap
        )
        SELECT c.date, c.security_id, c.ticker,
               r.bronze_security_name, r.resolved_instrument_type,
               r.resolved_exchange, c.market_cap_candidate, c.close,
               c.selected_shares_candidate, c.shares_filing_date,
               c.shares_period_date, c.shares_age_days,
               c.price_source, c.eodhd_share_source
        FROM peaks c
        LEFT JOIN silver.security_ticker_reference_resolution r
          ON r.security_id = c.security_id AND r.ticker = c.ticker
        WHERE c.rn = 1
        ORDER BY c.market_cap_candidate DESC
    """, [limit]).fetchall()


def main():
    with connect() as con:
        rows = build(con)
        outliers = top_eodhd_outliers(con)
    print("selected_source | issue_days | issues | priced_issue_days | largest_cap_candidate")
    for row in rows:
        print(*row, sep=" | ")
    print("TOP DISTINCT EODHD CAP CANDIDATES")
    print("date | security_id | ticker | name | instrument_type | exchange | cap | close | shares | filing_date | period_date | shares_age_days | price_source | share_source")
    for row in outliers:
        print(*row, sep=" | ")
    print("Candidate only: MSCI month-end close is effective on its calculation date; third-priority shares and cap outliers remain unresolved.")


if __name__ == "__main__":
    main()
