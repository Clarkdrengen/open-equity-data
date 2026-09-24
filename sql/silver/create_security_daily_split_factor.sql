DROP TABLE IF EXISTS silver.security_daily_split_factor;

CREATE TABLE silver.security_daily_split_factor AS

WITH price_dates AS (
    SELECT
        security_id,
        date
    FROM silver.security_daily_ohlcv
),

effective_splits AS (
    SELECT
        s.security_id,
        s.split_date AS date,

        CASE
            WHEN o.security_id IS NOT NULL
            THEN o.override_split_ratio
            ELSE s.split_ratio
        END AS effective_split_ratio

    FROM silver.security_split_event s

    LEFT JOIN silver.corporate_action_override o
      ON o.security_id = s.security_id
     AND o.event_date = s.split_date

    WHERE
        CASE
            WHEN o.security_id IS NOT NULL
            THEN o.override_split_ratio
            ELSE s.split_ratio
        END IS NOT NULL

      AND
        CASE
            WHEN o.security_id IS NOT NULL
            THEN o.override_split_ratio
            ELSE s.split_ratio
        END > 0
),

timeline AS (
    SELECT security_id, date
    FROM price_dates

    UNION

    SELECT security_id, date
    FROM effective_splits
),

daily AS (
    SELECT
        t.security_id,
        t.date,

        COALESCE(
            MAX(s.effective_split_ratio),
            1.0
        ) AS daily_split_ratio

    FROM timeline t

    LEFT JOIN effective_splits s
      ON s.security_id = t.security_id
     AND s.date = t.date

    GROUP BY 1, 2
),

factors AS (
    SELECT
        security_id,
        date,
        daily_split_ratio,

        SUM(
            LN(daily_split_ratio)
        ) OVER (
            PARTITION BY security_id
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_log_split_multiplier

    FROM daily
)

SELECT
    f.security_id,
    f.date,
    f.daily_split_ratio,

    EXP(
        f.cumulative_log_split_multiplier
    ) AS cumulative_split_multiplier,

    f.cumulative_log_split_multiplier

FROM factors f

JOIN price_dates p
  ON p.security_id = f.security_id
 AND p.date = f.date;
