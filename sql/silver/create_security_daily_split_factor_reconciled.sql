DROP TABLE IF EXISTS silver.security_daily_split_factor_reconciled;

CREATE TABLE silver.security_daily_split_factor_reconciled AS

WITH joined AS (
    SELECT
        f.security_id,
        f.date,

        f.daily_split_ratio AS original_daily_split_ratio,
        f.cumulative_split_multiplier AS original_cumulative_split_multiplier,
        f.cumulative_log_split_multiplier AS original_cumulative_log_split_multiplier,

        COALESCE(b.split_ratio, 1.0) AS automatic_backfill_ratio,

        f.daily_split_ratio * COALESCE(b.split_ratio, 1.0)
            AS daily_split_ratio

    FROM silver.security_daily_split_factor f

    LEFT JOIN silver.automatic_split_backfill b
      ON b.security_id = f.security_id
     AND b.split_date = f.date
),

cum AS (
    SELECT
        *,

        SUM(
            LN(automatic_backfill_ratio)
        ) OVER (
            PARTITION BY security_id
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_backfill_log_multiplier

    FROM joined
)

SELECT
    security_id,
    date,

    daily_split_ratio,

    original_cumulative_split_multiplier
        * EXP(cumulative_backfill_log_multiplier)
        AS cumulative_split_multiplier,

    original_cumulative_log_split_multiplier
        + cumulative_backfill_log_multiplier
        AS cumulative_log_split_multiplier,

    original_daily_split_ratio,
    original_cumulative_split_multiplier,
    automatic_backfill_ratio,

    (automatic_backfill_ratio <> 1.0)
        AS has_automatic_split_backfill

FROM cum;
