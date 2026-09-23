DROP TABLE IF EXISTS silver.security_daily_split_factor;

CREATE TABLE silver.security_daily_split_factor AS

WITH price_dates AS (
    SELECT
        security_id,
        date
    FROM silver.security_daily_ohlcv
),

split_dates AS (
    SELECT
        security_id,
        split_date AS date,
        split_ratio
    FROM silver.security_split_event
    WHERE split_ratio IS NOT NULL
      AND split_ratio > 0
),

-- Include split dates even where there is no OHLCV observation.
timeline AS (
    SELECT security_id, date
    FROM price_dates

    UNION

    SELECT security_id, date
    FROM split_dates
),

daily AS (
    SELECT
        t.security_id,
        t.date,

        COALESCE(
            MAX(s.split_ratio),
            1.0
        ) AS daily_split_ratio

    FROM timeline t

    LEFT JOIN split_dates s
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

-- Final table is on actual market observations only.
JOIN price_dates p
  ON p.security_id = f.security_id
 AND p.date = f.date;
