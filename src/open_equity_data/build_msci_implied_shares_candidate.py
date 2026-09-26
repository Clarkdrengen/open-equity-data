"""Build a Silver diagnostic of shares implied by MSCI cap and local prices.

The MSCI CSV's cap units and full-versus-float basis are unverified. This
candidate assumes USD millions and USD issue prices; it never replaces PIT
shares or enters portfolio weights automatically.
"""

from __future__ import annotations

import argparse

from open_equity_data.db import connect


SQL = """
CREATE OR REPLACE TABLE silver.msci_implied_shares_candidate AS
WITH source_rows AS (
    SELECT source_sha256, source_row_number, observation_date, isin,
           mktcap_as_supplied
    FROM silver.msci_usa_observation
    WHERE source_sha256 = ?
      AND parse_status = 'valid_isin'
      AND mktcap_as_supplied > 0
),
source_dates AS (
    SELECT source_sha256, observation_date, isin,
           MIN(source_row_number) AS source_row_number,
           MIN(mktcap_as_supplied) AS mktcap_as_supplied,
           COUNT(*) AS source_rows,
           COUNT(DISTINCT mktcap_as_supplied) AS distinct_cap_values
    FROM source_rows
    GROUP BY 1, 2, 3
),
priced_matches AS (
    SELECT s.*, u.security_id, u.ticker, u.date AS price_date,
           p.close AS raw_close,
           ROW_NUMBER() OVER (
               PARTITION BY s.source_sha256, s.observation_date, s.isin,
                            u.security_id
               ORDER BY u.date DESC, u.ticker
           ) AS latest_price_rank
    FROM source_dates s
    JOIN silver.research_universe_eligibility u
      ON UPPER(TRIM(u.isin)) = s.isin
     AND u.date BETWEEN s.observation_date - INTERVAL 7 DAY
                    AND s.observation_date
     AND u.primary_research_eligible_exchange
    JOIN silver.security_daily_ohlcv p
      ON p.security_id = u.security_id
     AND p.date = u.date
     AND p.ticker = u.ticker
     AND p.close > 0
),
latest_prices AS (
    SELECT * EXCLUDE (latest_price_rank)
    FROM priced_matches WHERE latest_price_rank = 1
),
match_counts AS (
    SELECT source_sha256, observation_date, isin,
           COUNT(DISTINCT security_id) AS matched_security_count
    FROM latest_prices
    GROUP BY 1, 2, 3
)
SELECT p.source_sha256, p.source_row_number, p.observation_date,
       p.isin, p.source_rows, p.distinct_cap_values,
       p.security_id, p.ticker, p.price_date,
       date_diff('day', p.price_date, p.observation_date) AS price_lag_days,
       p.mktcap_as_supplied, p.raw_close, m.matched_security_count,
       CASE WHEN p.distinct_cap_values > 1
                 THEN 'conflicting_source_caps'
            WHEN m.matched_security_count > 1
                 THEN 'ambiguous_security_id'
            ELSE 'candidate_usd_millions_assumed' END AS candidate_status,
       CASE WHEN p.distinct_cap_values = 1 AND m.matched_security_count = 1
            THEN p.mktcap_as_supplied * 1000000.0 / p.raw_close
            ELSE NULL END AS implied_shares_usd_millions_assumed
FROM latest_prices p
JOIN match_counts m USING (source_sha256, observation_date, isin)
"""

COMPARISON_SQL = """
CREATE OR REPLACE TABLE silver.msci_implied_shares_scale_audit AS
WITH joined AS (
    SELECT c.*, p.shares_outstanding AS eodhd_pit_shares,
           p.shares_filing_date AS eodhd_shares_filing_date,
           p.shares_age_days AS eodhd_shares_age_days,
           p.shares_pit_available AS eodhd_pit_available,
           p.ticker_identity_ambiguous AS eodhd_identity_ambiguous
    FROM silver.msci_implied_shares_candidate c
    LEFT JOIN silver.security_daily_shares_outstanding_pit p
      ON p.security_id = c.security_id
     AND p.date = c.price_date
     AND p.ticker = c.ticker
), ratios AS (
    SELECT *,
           CASE WHEN candidate_status = 'candidate_usd_millions_assumed'
                      AND eodhd_pit_available
                      AND NOT COALESCE(eodhd_identity_ambiguous, FALSE)
                      AND eodhd_pit_shares > 0
                THEN implied_shares_usd_millions_assumed / eodhd_pit_shares
                ELSE NULL END AS implied_to_eodhd_ratio
    FROM joined
)
SELECT *,
       CASE WHEN implied_to_eodhd_ratio IS NULL THEN 'not_comparable'
            WHEN implied_to_eodhd_ratio BETWEEN 800 AND 1250
                 THEN 'near_1000x_high'
            WHEN implied_to_eodhd_ratio BETWEEN 0.0008 AND 0.00125
                 THEN 'near_1000x_low'
            WHEN implied_to_eodhd_ratio BETWEEN 0.8 AND 1.25
                 THEN 'near_1x'
            ELSE 'other_ratio' END AS scale_diagnostic
FROM ratios
"""


def build(con, digest: str | None = None):
    if digest is None:
        sources = con.execute("""
            SELECT DISTINCT source_sha256 FROM silver.msci_usa_observation
        """).fetchall()
        if len(sources) != 1:
            raise ValueError("Specify --source-sha256 when Silver holds multiple files")
        digest = sources[0][0]
    con.execute(SQL, [digest])
    con.execute(COMPARISON_SQL)
    return con.execute("""
        SELECT candidate_status, scale_diagnostic, COUNT(*), COUNT(DISTINCT security_id),
               MIN(observation_date), MAX(observation_date)
        FROM silver.msci_implied_shares_scale_audit
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256")
    args = parser.parse_args()
    with connect() as con:
        for status, scale, rows, issues, first, last in build(con, args.source_sha256):
            print(status, scale, rows, issues, first, last)
    print("Candidate assumes MSCI cap in USD millions and raw close in USD;"
          " source cap basis and publication timing are unverified."
          " Ratios to EODHD PIT shares are diagnostic; split and class basis may differ.")


if __name__ == "__main__":
    main()
