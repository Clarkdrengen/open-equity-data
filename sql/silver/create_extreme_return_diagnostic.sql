DROP TABLE IF EXISTS silver.extreme_return_diagnostic;

CREATE TABLE silver.extreme_return_diagnostic AS
SELECT
    c.*,

    CASE
        WHEN c.comparison_status IN (
            'provider_symbol_not_found',
            'provider_price_pair_missing',
            'provider_request_failed',
            'no_provider_request'
        )
        THEN 'provider_unavailable'

        WHEN ABS(c.dolt_gross_total_return) > 1.0
         AND ABS(c.dolt_price_return) <= 1.0
         AND ABS(c.provider_raw_return) <= 1.0
        THEN 'dividend_or_distribution_anomaly'

        WHEN ABS(c.dolt_price_return) > 1.0
         AND ABS(c.provider_raw_return) <= 1.0
        THEN 'dolt_price_disagreement'

        WHEN ABS(c.provider_raw_return) > 1.0
         AND c.provider_adjusted_return IS NOT NULL
         AND ABS(c.provider_adjusted_return) <= 1.0
        THEN 'corporate_action_candidate'

        WHEN ABS(c.provider_raw_return) > 1.0
         AND c.provider_adjusted_return IS NOT NULL
         AND ABS(c.provider_adjusted_return) > 1.0
        THEN 'vendor_confirms_extreme_after_adjustment'

        WHEN ABS(c.provider_raw_return) > 1.0
         AND c.provider_adjusted_return IS NULL
        THEN 'vendor_raw_extreme_adjusted_missing'

        ELSE 'other'
    END AS diagnostic_class,

    CASE
        WHEN c.provider_to_dolt_previous_close_ratio IS NULL
          OR c.provider_to_dolt_current_close_ratio IS NULL
        THEN 'not_comparable'

        WHEN c.provider_to_dolt_previous_close_ratio BETWEEN 0.8 AND 1.25
         AND c.provider_to_dolt_current_close_ratio BETWEEN 0.8 AND 1.25
        THEN 'price_levels_agree'

        WHEN NOT (
            c.provider_to_dolt_previous_close_ratio BETWEEN 0.8 AND 1.25
        )
         AND c.provider_to_dolt_current_close_ratio BETWEEN 0.8 AND 1.25
        THEN 'previous_dolt_price_scale_mismatch'

        WHEN c.provider_to_dolt_previous_close_ratio BETWEEN 0.8 AND 1.25
         AND NOT (
            c.provider_to_dolt_current_close_ratio BETWEEN 0.8 AND 1.25
        )
        THEN 'current_dolt_price_scale_mismatch'

        ELSE 'both_price_levels_differ'
    END AS price_level_diagnostic

FROM silver.extreme_return_price_comparison c;
