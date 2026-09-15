CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.split_audit AS
WITH prices AS (
    SELECT
        date,
        act_symbol,
        close,
        LAG(date) OVER (
            PARTITION BY act_symbol
            ORDER BY date
        ) AS previous_trading_date,
        LAG(close) OVER (
            PARTITION BY act_symbol
            ORDER BY date
        ) AS previous_close
    FROM bronze.ohlcv
),
split_base AS (
    SELECT
        act_symbol,
        ex_date,
        to_factor,
        for_factor,
        CAST(to_factor / NULLIF(for_factor, 0) AS DOUBLE) AS stated_ratio
    FROM bronze.split
),
nearby_same_ratio AS (
    SELECT
        s1.act_symbol,
        s1.ex_date,
        s1.stated_ratio,
        COUNT(*) - 1 AS nearby_same_ratio_count
    FROM split_base s1
    JOIN split_base s2
      ON s1.act_symbol = s2.act_symbol
     AND s1.stated_ratio = s2.stated_ratio
     AND ABS(DATE_DIFF('day', s1.ex_date, s2.ex_date)) <= 30
    GROUP BY
        s1.act_symbol,
        s1.ex_date,
        s1.stated_ratio
)
SELECT
    s.act_symbol,
    s.ex_date AS source_ex_date,
    s.to_factor,
    s.for_factor,
    s.stated_ratio,

    p.previous_trading_date,
    p.previous_close,
    p.close AS event_close,

    CAST(
        p.close / NULLIF(p.previous_close, 0)
        AS DOUBLE
    ) AS raw_price_ratio,

    CAST(
        p.close * s.stated_ratio
        / NULLIF(p.previous_close, 0) - 1
        AS DOUBLE
    ) AS implied_return,

    p.close IS NOT NULL AS has_price_on_ex_date,

    COALESCE(n.nearby_same_ratio_count, 0) AS nearby_same_ratio_count,

    CASE
        WHEN p.close IS NULL THEN TRUE
        WHEN ABS(
            p.close * s.stated_ratio
            / NULLIF(p.previous_close, 0) - 1
        ) > 0.50 THEN TRUE
        WHEN COALESCE(n.nearby_same_ratio_count, 0) > 0 THEN TRUE
        ELSE FALSE
    END AS suspicious_flag

FROM split_base s
LEFT JOIN prices p
  ON p.act_symbol = s.act_symbol
 AND p.date = s.ex_date
LEFT JOIN nearby_same_ratio n
  ON n.act_symbol = s.act_symbol
 AND n.ex_date = s.ex_date
 AND n.stated_ratio = s.stated_ratio;
