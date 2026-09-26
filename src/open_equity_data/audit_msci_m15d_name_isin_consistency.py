"""Audit dated MSCI code/name/ISIN agreement and priced-issue overlap."""

from __future__ import annotations

from open_equity_data.db import connect


IDENTITY_SQL = """
CREATE OR REPLACE TABLE silver.msci_m15d_identity_candidate AS
WITH extension AS (
    SELECT observation_date, msci_security_code,
           MIN(security_name) AS extension_name,
           MIN(msci_issuer_code) AS extension_issuer_code,
           MIN(msci_timeseries_code) AS extension_timeseries_code,
           MIN(shares_today) AS shares_today,
           MIN(closing_shares) AS closing_shares,
           MIN(scap_fif_raw) AS scap_fif_raw,
           MIN(historical_gimi_fif_raw) AS historical_gimi_fif_raw,
           COUNT(*) AS extension_rows,
           COUNT(DISTINCT security_name) AS extension_name_variants,
           COUNT(DISTINCT msci_issuer_code) AS extension_issuer_codes,
           COUNT(DISTINCT msci_timeseries_code) AS extension_timeseries_codes,
           COUNT(DISTINCT COALESCE(shares_today, -1) || ':' || COALESCE(closing_shares, -1)) AS share_variants
    FROM silver.msci_m15d_security_observation
    WHERE observation_date IS NOT NULL AND msci_security_code <> ''
    GROUP BY 1, 2
), rif AS (
    SELECT observation_date, msci_security_code,
           MIN(security_name) AS rif_name,
           MIN(msci_issuer_code) AS rif_issuer_code,
           MIN(msci_timeseries_code) AS rif_timeseries_code,
           MIN(isin) FILTER (WHERE parse_status = 'valid_isin') AS isin,
           COUNT(*) AS rif_rows,
           COUNT(DISTINCT security_name) AS rif_name_variants,
           COUNT(DISTINCT isin) FILTER (WHERE parse_status = 'valid_isin') AS distinct_valid_isins,
           COUNT(DISTINCT msci_issuer_code) AS rif_issuer_codes,
           COUNT(DISTINCT msci_timeseries_code) AS rif_timeseries_codes,
           COUNT(*) FILTER (WHERE parse_status <> 'valid_isin') AS invalid_isin_rows
    FROM silver.msci_m15d_rif_observation
    WHERE observation_date IS NOT NULL AND msci_security_code <> ''
    GROUP BY 1, 2
), paired AS (
    SELECT e.*, r.rif_name, r.rif_issuer_code, r.rif_timeseries_code,
           r.isin, r.rif_rows, r.rif_name_variants, r.distinct_valid_isins,
           r.rif_issuer_codes, r.rif_timeseries_codes, r.invalid_isin_rows,
           regexp_replace(upper(trim(e.extension_name)), '[^A-Z0-9]', '', 'g') =
           regexp_replace(upper(trim(r.rif_name)), '[^A-Z0-9]', '', 'g')
             AS normalized_name_agreement
    FROM extension e
    LEFT JOIN rif r USING (observation_date, msci_security_code)
)
SELECT *,
       CASE WHEN rif_rows IS NULL THEN 'no_rif_code_date'
            WHEN distinct_valid_isins <> 1 OR invalid_isin_rows > 0
                 THEN 'invalid_or_conflicting_isin'
            WHEN share_variants <> 1 OR extension_name_variants <> 1
              OR rif_name_variants <> 1 OR extension_issuer_codes <> 1
              OR extension_timeseries_codes <> 1 OR rif_issuer_codes <> 1
              OR rif_timeseries_codes <> 1 THEN 'conflicting_source_rows'
            WHEN extension_issuer_code <> rif_issuer_code
              OR extension_timeseries_code <> rif_timeseries_code
                 THEN 'msci_code_disagreement'
            WHEN NOT COALESCE(normalized_name_agreement, FALSE) THEN 'name_review'
            ELSE 'candidate_exact_code_name' END AS identity_status
FROM paired
"""

OVERLAP_SQL = """
CREATE OR REPLACE TABLE silver.msci_m15d_price_overlap_candidate AS
WITH matches AS (
    SELECT c.observation_date, c.msci_security_code, c.isin,
           c.extension_name, c.rif_name, c.identity_status,
           c.shares_today, c.closing_shares, c.scap_fif_raw,
           c.historical_gimi_fif_raw, u.security_id, u.ticker,
           u.date AS price_date, p.close AS raw_close,
           ROW_NUMBER() OVER (
               PARTITION BY c.observation_date, c.msci_security_code,
                            u.security_id
               ORDER BY u.date DESC
           ) AS price_rank
    FROM silver.msci_m15d_identity_candidate c
    JOIN silver.research_universe_eligibility u
      ON UPPER(TRIM(u.isin)) = c.isin
     AND u.date BETWEEN c.observation_date - INTERVAL 7 DAY
                    AND c.observation_date
     AND u.primary_research_eligible_exchange
    JOIN silver.security_daily_ohlcv p
      ON p.security_id = u.security_id
     AND p.date = u.date AND p.ticker = u.ticker
     AND p.close > 0
    WHERE c.identity_status IN ('candidate_exact_code_name', 'name_review')
), latest AS (
    SELECT * EXCLUDE (price_rank) FROM matches WHERE price_rank = 1
)
SELECT *, COUNT(DISTINCT security_id) OVER (
    PARTITION BY observation_date, msci_security_code
) AS project_security_matches
FROM latest
"""


def build(con):
    con.execute(IDENTITY_SQL)
    con.execute(OVERLAP_SQL)
    statuses = con.execute("""
        SELECT identity_status, COUNT(*),
               COUNT(*) FILTER (WHERE normalized_name_agreement),
               MIN(observation_date), MAX(observation_date)
        FROM silver.msci_m15d_identity_candidate
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    overlap = con.execute("""
        SELECT identity_status, COUNT(*), COUNT(DISTINCT security_id),
               COUNT(*) FILTER (WHERE project_security_matches > 1)
        FROM silver.msci_m15d_price_overlap_candidate
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    return statuses, overlap


def main():
    with connect() as con:
        statuses, overlap = build(con)
    print("identity_status | MSCI code-dates | normalized-name-agreements | first | last")
    for row in statuses:
        print(*row, sep=" | ")
    print("price_overlap_status | issue-dates | security_ids | multi-security rows")
    for row in overlap:
        print(*row, sep=" | ")
    print("Candidates only; date/code/name/ISIN agreement is not a canonical identity approval.")


if __name__ == "__main__":
    main()
