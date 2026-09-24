DROP TABLE IF EXISTS silver.split_backfill_validation;

CREATE TABLE silver.split_backfill_validation AS
SELECT
    c.*,

    CASE
        WHEN provider_raw_return IS NOT NULL
         AND provider_split_ratio IS NOT NULL
        THEN (1.0 + provider_raw_return) * provider_split_ratio - 1.0
        ELSE NULL
    END AS counterfactual_return_with_provider_split,

    CASE
        WHEN provider_raw_return IS NOT NULL
         AND provider_split_ratio IS NOT NULL
         AND provider_adjusted_return IS NOT NULL
        THEN ABS(
            ((1.0 + provider_raw_return) * provider_split_ratio - 1.0)
            - provider_adjusted_return
        )
        ELSE NULL
    END AS adjusted_return_abs_error,

    CASE
        WHEN split_comparison_status = 'exact_date_ratio_conflict'
         AND ABS(daily_split_ratio - 1.0) < 1e-12
         AND provider_split_ratio IS NOT NULL
         AND provider_adjusted_return IS NOT NULL
         AND ABS(
            ((1.0 + provider_raw_return) * provider_split_ratio - 1.0)
            - provider_adjusted_return
         ) < 1e-6
        THEN TRUE
        ELSE FALSE
    END AS exact_date_missing_split_validated

FROM silver.corporate_action_candidate_split_comparison c;
