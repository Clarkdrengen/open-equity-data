DROP TABLE IF EXISTS silver.security_gtr_index;

CREATE TABLE silver.security_gtr_index AS

WITH flagged AS (
    SELECT
        *,

        SUM(
            CASE
                WHEN NOT final_research_eligible
                THEN 1
                ELSE 0
            END
        ) OVER (
            PARTITION BY security_id
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS return_segment_id

    FROM silver.security_daily_return_research
),

indexed AS (
    SELECT
        *,

        SUM(
            CASE
                WHEN final_research_eligible
                THEN LN(1.0 + gross_total_return)
                ELSE NULL
            END
        ) OVER (
            PARTITION BY
                security_id,
                return_segment_id
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS cumulative_gtr_log

    FROM flagged
)

SELECT
    security_id,
    ticker,
    date,

    gross_total_return,

    final_research_eligible,
    research_quarantine_reason,
    diagnostic_class,

    return_segment_id,

    CASE
        WHEN final_research_eligible
        THEN cumulative_gtr_log
        ELSE NULL
    END AS cumulative_gtr_log,

    CASE
        WHEN final_research_eligible
        THEN EXP(cumulative_gtr_log)
        ELSE NULL
    END AS gross_total_return_index

FROM indexed;
