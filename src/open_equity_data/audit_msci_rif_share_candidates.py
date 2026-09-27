"""Measure RIF share evidence at dated priced-issue matches, without overrides."""

import argparse

from open_equity_data.db import connect


def build(con, family: str = "m15d"):
    if family not in {"m15d", "m15e"}:
        raise ValueError("Unknown MSCI source family")
    source = f"silver.msci_{family}_rif_share_observation"
    overlap = f"silver.msci_{family}_price_overlap_candidate"
    target = f"silver.msci_{family}_rif_share_overlap_audit"
    con.execute(f"""
        CREATE OR REPLACE TABLE {target} AS
        WITH source AS (
            SELECT observation_date, msci_security_code, isin,
                   COUNT(*) AS rif_source_rows,
                   COUNT(DISTINCT closing_shares) FILTER
                       (WHERE closing_shares > 0) AS closing_share_variants,
                   COUNT(DISTINCT shares_today) FILTER
                       (WHERE shares_today > 0) AS today_share_variants,
                   MIN(closing_shares) FILTER
                       (WHERE closing_shares > 0) AS rif_closing_shares,
                   MIN(shares_today) FILTER
                       (WHERE shares_today > 0) AS rif_shares_today,
                   MIN(shares_next_day) FILTER
                       (WHERE shares_next_day > 0) AS rif_shares_next_day,
                   MIN(price_currency) AS rif_price_currency,
                   MIN(closing_cap_usd_raw) AS rif_closing_cap_usd_raw
            FROM {source}
            WHERE observation_date IS NOT NULL
            GROUP BY 1, 2, 3
        ), paired AS (
            SELECT o.observation_date, o.msci_security_code, o.isin,
                   o.security_id, o.ticker, o.price_date,
                   o.identity_status, o.project_security_matches,
                   s.rif_source_rows, s.closing_share_variants,
                   s.today_share_variants, s.rif_closing_shares,
                   s.rif_shares_today, s.rif_shares_next_day,
                   s.rif_price_currency, s.rif_closing_cap_usd_raw,
                   p.shares_outstanding AS eodhd_pit_shares,
                   p.shares_period_date AS eodhd_shares_period_date,
                   p.shares_filing_date AS eodhd_shares_filing_date,
                   p.shares_pit_available AS eodhd_pit_available,
                   p.ticker_identity_ambiguous AS eodhd_ticker_ambiguous,
                   CASE WHEN p.shares_period_date IS NOT NULL THEN EXISTS (
                       SELECT 1 FROM silver.security_daily_split_factor_reconciled f
                       WHERE f.security_id = o.security_id
                         AND f.date > p.shares_period_date
                         AND f.date <= o.price_date
                         AND ABS(f.daily_split_ratio - 1.0) > 0.000001
                   ) ELSE FALSE END AS intervening_split
            FROM {overlap} o
            LEFT JOIN source s
              ON s.observation_date = o.observation_date
             AND s.msci_security_code = o.msci_security_code
             AND s.isin = o.isin
            LEFT JOIN silver.security_daily_shares_outstanding_pit p
              ON p.security_id = o.security_id
             AND p.date = o.price_date AND p.ticker = o.ticker
        ), gated AS (
            SELECT *,
                   identity_status = 'candidate_exact_code_name'
                   AND project_security_matches = 1
                   AND COALESCE(eodhd_pit_available, FALSE)
                   AND NOT COALESCE(eodhd_ticker_ambiguous, FALSE)
                   AND NOT intervening_split
                   AND eodhd_pit_shares > 0 AS comparable_basis
            FROM paired
        )
        SELECT *,
               CASE WHEN comparable_basis AND closing_share_variants = 1
                         AND rif_closing_shares > 0
                    THEN rif_closing_shares / eodhd_pit_shares END
                    AS closing_to_eodhd_ratio,
               CASE WHEN comparable_basis AND today_share_variants = 1
                         AND rif_shares_today > 0
                    THEN rif_shares_today / eodhd_pit_shares END
                    AS today_to_eodhd_ratio
        FROM gated
    """)
    return con.execute(f"""
        SELECT COUNT(*) AS matched_snapshots,
               COUNT(DISTINCT security_id) AS matched_issues,
               COUNT(*) FILTER (WHERE rif_closing_shares > 0) AS closing_share_rows,
               COUNT(*) FILTER (WHERE rif_shares_today > 0) AS today_share_rows,
               COUNT(*) FILTER (WHERE eodhd_pit_shares > 0
                                    AND COALESCE(eodhd_pit_available, FALSE))
                   AS eodhd_share_rows,
               COUNT(*) FILTER (WHERE comparable_basis) AS comparable_basis_rows,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio IS NOT NULL)
                   AS closing_ratios,
               COUNT(*) FILTER (WHERE today_to_eodhd_ratio IS NOT NULL)
                   AS today_ratios,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio BETWEEN 800 AND 1250)
                   AS closing_near_1000x_high,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio BETWEEN 0.0008 AND 0.00125)
                   AS closing_near_1000x_low,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio BETWEEN 800000 AND 1250000)
                   AS closing_near_million_high,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio BETWEEN 0.0000008 AND 0.00000125)
                   AS closing_near_million_low,
               COUNT(*) FILTER (WHERE closing_to_eodhd_ratio BETWEEN 0.8 AND 1.25)
                   AS closing_near_1x,
               COUNT(*) FILTER (WHERE closing_share_variants > 1) AS conflicting_closing_rows
        FROM {target}
    """).fetchone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["m15d", "m15e"], default="m15d")
    args = parser.parse_args()
    with connect() as con:
        row = build(con, args.family)
    names = (
        "matched_snapshots", "matched_issues", "closing_share_rows",
        "today_share_rows", "eodhd_share_rows", "comparable_basis_rows",
        "closing_ratios", "today_ratios", "closing_near_1000x_high",
        "closing_near_1000x_low", "closing_near_million_high",
        "closing_near_million_low", "closing_near_1x",
        "conflicting_closing_rows",
    )
    print(args.family.upper(), "RIF share overlap:", dict(zip(names, row)))
    print("Month-end raw-value ratios only; no share-unit multiplier or source availability approved.")


if __name__ == "__main__":
    main()
