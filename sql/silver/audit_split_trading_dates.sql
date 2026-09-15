WITH missing_date_splits AS (
    SELECT
        act_symbol,
        source_ex_date,
        stated_ratio
    FROM silver.split_audit
    WHERE NOT has_price_on_ex_date
),

candidate_dates AS (
    SELECT
        s.act_symbol,
        s.source_ex_date,
        s.stated_ratio,
        MIN(p.date) AS candidate_trading_date
    FROM missing_date_splits s
    JOIN bronze.ohlcv p
      ON p.act_symbol = s.act_symbol
     AND p.date >= s.source_ex_date
     AND p.date <= s.source_ex_date + INTERVAL 7 DAY
    GROUP BY
        s.act_symbol,
        s.source_ex_date,
        s.stated_ratio
),

prices AS (
    SELECT
        act_symbol,
        date,
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
)

SELECT
    c.act_symbol,
    c.source_ex_date,
    c.candidate_trading_date,
    c.stated_ratio,
    p.previous_trading_date,
    p.previous_close,
    p.close AS event_close,

    CAST(
        p.close * c.stated_ratio
        / NULLIF(p.previous_close, 0) - 1
        AS DOUBLE
    ) AS implied_return,

    DATE_DIFF(
        'day',
        c.source_ex_date,
        c.candidate_trading_date
    ) AS calendar_days_shift

FROM candidate_dates c
JOIN prices p
  ON p.act_symbol = c.act_symbol
 AND p.date = c.candidate_trading_date

ORDER BY
    calendar_days_shift DESC,
    ABS(implied_return) DESC;
