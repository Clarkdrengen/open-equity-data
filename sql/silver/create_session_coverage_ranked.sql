CREATE OR REPLACE TABLE silver.session_coverage_ranked AS

SELECT
    *,
    PERCENT_RANK() OVER (
        PARTITION BY is_early_close
        ORDER BY continuity_coverage_pct
    ) AS coverage_percentile,

    CASE
        WHEN continuity_coverage_pct < 80
            THEN 'extreme_anomaly'

        WHEN PERCENT_RANK() OVER (
            PARTITION BY is_early_close
            ORDER BY continuity_coverage_pct
        ) <= 0.01
            THEN 'very_low_for_session_type'

        WHEN PERCENT_RANK() OVER (
            PARTITION BY is_early_close
            ORDER BY continuity_coverage_pct
        ) <= 0.05
            THEN 'low_for_session_type'

        ELSE 'typical_for_session_type'
    END AS coverage_diagnostic

FROM silver.session_coverage_audit;
