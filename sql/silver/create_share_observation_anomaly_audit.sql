-- Diagnostic only. One row per issue/EODHD source observation, including
-- observations that the market-cap candidate did not select.
CREATE OR REPLACE TABLE silver.share_observation_anomaly_audit AS
WITH priced AS (
    SELECT security_id, ticker, date, eodhd_provider_symbol,
           shares_period_date, shares_filing_date, eodhd_filed_shares,
           eodhd_normalized_shares, eodhd_basis_status,
           selected_source, market_cap_candidate, close,
           msci_current_shares_candidate, manual_current_shares_candidate,
           current_split_multiplier, eodhd_observation_invalidated
    FROM silver.security_daily_market_cap_source_priority_candidate
    WHERE eodhd_filed_shares > 0 AND shares_filing_date IS NOT NULL
      AND close > 0
), observations AS (
    SELECT security_id, eodhd_provider_symbol, shares_period_date,
           shares_filing_date, eodhd_filed_shares,
           MIN(ticker) AS ticker,
           MIN(date) AS first_price_date, MAX(date) AS last_price_date,
           COUNT(*) AS priced_days,
           COUNT(*) FILTER (WHERE selected_source = 'eodhd') AS selected_days,
           MAX(market_cap_candidate) FILTER (WHERE selected_source = 'eodhd')
               AS max_selected_cap,
           MAX(close * eodhd_filed_shares) AS max_raw_cap,
           BOOL_OR(eodhd_observation_invalidated) AS invalidated,
           -- A calibrated count is preferable. Unverified raw counts remain
           -- visible, but their comparisons must not establish a correction.
           MEDIAN(CASE WHEN eodhd_normalized_shares > 0
                           AND current_split_multiplier > 0
                       THEN eodhd_normalized_shares /
                            current_split_multiplier END) AS share_basis_proxy,
           BOOL_OR(eodhd_basis_status IN (
               'no_later_recorded_split', 'retrospective_confirmed',
               'contemporaneous_confirmed')) AS any_comparable_basis,
           MAX(ABS(LN(eodhd_normalized_shares /
                      msci_current_shares_candidate))) FILTER (
               WHERE eodhd_normalized_shares > 0
                 AND msci_current_shares_candidate > 0) AS max_msci_log_ratio,
           MAX(ABS(LN(eodhd_normalized_shares /
                      manual_current_shares_candidate))) FILTER (
               WHERE eodhd_normalized_shares > 0
                 AND manual_current_shares_candidate > 0) AS max_manual_log_ratio
    FROM priced
    GROUP BY 1, 2, 3, 4, 5
), levels AS (
    SELECT *, LN(share_basis_proxy) AS log_shares,
           MEDIAN(LN(share_basis_proxy)) OVER (PARTITION BY security_id)
               AS median_log_shares,
           COUNT(*) OVER (PARTITION BY security_id) AS observations_for_issue,
           LAG(share_basis_proxy) OVER (
               PARTITION BY security_id
               ORDER BY shares_filing_date, shares_period_date,
                        eodhd_provider_symbol, eodhd_filed_shares)
               AS prior_share_basis_proxy
    FROM observations
), dispersion AS (
    SELECT *, MEDIAN(ABS(log_shares - median_log_shares)) OVER (
               PARTITION BY security_id) AS mad_log_shares
    FROM levels
), scored AS (
    SELECT *,
           CASE WHEN observations_for_issue >= 4 AND mad_log_shares > 0
                THEN 0.67448975 * ABS(log_shares - median_log_shares)
                     / mad_log_shares END AS robust_z,
           CASE WHEN prior_share_basis_proxy > 0
                THEN ABS(LN(share_basis_proxy / prior_share_basis_proxy))
                END AS adjacent_log_ratio,
           GREATEST(max_msci_log_ratio, max_manual_log_ratio)
               AS cross_source_log_ratio
    FROM dispersion
)
SELECT security_id, ticker, eodhd_provider_symbol, shares_period_date,
       shares_filing_date, eodhd_filed_shares, share_basis_proxy,
       first_price_date, last_price_date, priced_days, selected_days,
       max_selected_cap, max_raw_cap, invalidated, any_comparable_basis,
       observations_for_issue, robust_z, adjacent_log_ratio,
       max_msci_log_ratio, max_manual_log_ratio, cross_source_log_ratio,
       CASE
         WHEN cross_source_log_ratio >= LN(10) THEN 'cross_source_10x'
         WHEN any_comparable_basis AND adjacent_log_ratio >= LN(10)
           THEN 'adjacent_10x'
         WHEN any_comparable_basis AND robust_z >= 8 THEN 'robust_z_8'
         WHEN cross_source_log_ratio >= LN(2) THEN 'cross_source_2x'
         WHEN any_comparable_basis AND adjacent_log_ratio >= LN(2)
           THEN 'adjacent_2x'
         WHEN any_comparable_basis AND robust_z >= 5 THEN 'robust_z_5'
         WHEN max_selected_cap >= 500000000000
              AND max_msci_log_ratio IS NULL
              AND max_manual_log_ratio IS NULL THEN 'large_cap_unverified'
         ELSE 'no_flag'
       END AS review_reason
FROM scored;
