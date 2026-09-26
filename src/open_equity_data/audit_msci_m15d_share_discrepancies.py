"""Compare overlapping MSCI and EODHD shares without changing either source."""

from __future__ import annotations

from open_equity_data.db import connect


SQL = """
CREATE OR REPLACE TABLE silver.msci_m15d_share_discrepancy_audit AS
WITH paired AS (
    SELECT m.*, p.shares_outstanding AS eodhd_pit_shares,
           p.shares_period_date AS eodhd_shares_period_date,
           p.shares_filing_date AS eodhd_shares_filing_date,
           p.shares_age_days AS eodhd_shares_age_days,
           p.shares_pit_available AS eodhd_pit_available,
           p.ticker_identity_ambiguous AS eodhd_ticker_ambiguous,
           CASE WHEN p.shares_period_date IS NOT NULL THEN EXISTS (
               SELECT 1 FROM silver.security_daily_split_factor_reconciled f
               WHERE f.security_id = m.security_id
                 AND f.date > p.shares_period_date
                 AND f.date <= m.price_date
                 AND ABS(f.daily_split_ratio - 1.0) > 0.000001
           ) ELSE FALSE END AS intervening_split
    FROM silver.msci_m15d_price_overlap_candidate m
    LEFT JOIN silver.security_daily_shares_outstanding_pit p
      ON p.security_id = m.security_id
     AND p.date = m.price_date AND p.ticker = m.ticker
), eligible AS (
    SELECT *,
           identity_status = 'candidate_exact_code_name'
           AND project_security_matches = 1
           AND COALESCE(eodhd_pit_available, FALSE)
           AND NOT COALESCE(eodhd_ticker_ambiguous, FALSE)
           AND NOT intervening_split
           AND eodhd_pit_shares > 0 AS comparable
    FROM paired
), ratios AS (
    SELECT *,
           CASE WHEN comparable AND shares_today > 0
                THEN shares_today / eodhd_pit_shares END AS today_to_eodhd_ratio,
           CASE WHEN comparable AND closing_shares > 0
                THEN closing_shares / eodhd_pit_shares END AS closing_to_eodhd_ratio
    FROM eligible
)
SELECT *,
       CASE WHEN today_to_eodhd_ratio IS NULL THEN 'not_comparable'
            WHEN today_to_eodhd_ratio BETWEEN 800 AND 1250 THEN 'near_1000x_high'
            WHEN today_to_eodhd_ratio BETWEEN 0.0008 AND 0.00125 THEN 'near_1000x_low'
            WHEN today_to_eodhd_ratio BETWEEN 0.8 AND 1.25 THEN 'near_1x'
            ELSE 'other_ratio' END AS today_scale_band,
       CASE WHEN closing_to_eodhd_ratio IS NULL THEN 'not_comparable'
            WHEN closing_to_eodhd_ratio BETWEEN 800 AND 1250 THEN 'near_1000x_high'
            WHEN closing_to_eodhd_ratio BETWEEN 0.0008 AND 0.00125 THEN 'near_1000x_low'
            WHEN closing_to_eodhd_ratio BETWEEN 0.8 AND 1.25 THEN 'near_1x'
            ELSE 'other_ratio' END AS closing_scale_band
FROM ratios
"""


def build(con):
    con.execute(SQL)
    return con.execute("""
        SELECT identity_status, today_scale_band, closing_scale_band,
               COUNT(*) AS issue_dates, COUNT(DISTINCT security_id) AS issues,
               COUNT(*) FILTER (WHERE intervening_split) AS split_overlap,
               MIN(observation_date), MAX(observation_date)
        FROM silver.msci_m15d_share_discrepancy_audit
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """).fetchall()


def main():
    with connect() as con:
        rows = build(con)
    print("identity | today_band | closing_band | issue_dates | issues | split_overlap | first | last")
    for row in rows:
        print(*row, sep=" | ")
    print("Raw source comparison only; no automatic 1000x rescaling or share override.")


if __name__ == "__main__":
    main()
