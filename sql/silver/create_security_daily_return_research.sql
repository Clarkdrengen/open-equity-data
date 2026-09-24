DROP TABLE IF EXISTS silver.security_daily_return_research;

CREATE TABLE silver.security_daily_return_research AS

WITH classified AS (
    SELECT
        r.*,

        d.diagnostic_class,
        d.price_level_diagnostic,

        CASE
            WHEN NOT r.research_eligible
            THEN 'base_return_not_eligible:' || r.return_status

            WHEN r.gross_total_return IS NULL
            THEN 'null_gross_total_return'

            WHEN r.gross_total_return <= -1.0
            THEN 'nonpositive_wealth_factor'

            WHEN ABS(r.gross_total_return) > 1.0
             AND COALESCE(
                    d.diagnostic_class,
                    'unclassified_extreme_return'
                 ) <> 'vendor_confirms_extreme_after_adjustment'
            THEN 'extreme_return:' ||
                 COALESCE(
                     d.diagnostic_class,
                     'unclassified_extreme_return'
                 )

            ELSE NULL
        END AS research_quarantine_reason

    FROM silver.security_daily_return r

    LEFT JOIN silver.extreme_return_diagnostic d
      ON d.security_id = r.security_id
     AND d.date = r.date
)

SELECT
    *,

    (research_quarantine_reason IS NULL)
        AS final_research_eligible

FROM classified;
