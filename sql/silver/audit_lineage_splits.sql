WITH split_events AS (
    SELECT
        s.act_symbol,
        s.ex_date,
        CAST(s.to_factor / NULLIF(s.for_factor, 0) AS DOUBLE) AS stated_ratio,

        m.lineage_id,
        lm.lineage_code

    FROM bronze.split s

    JOIN silver.ticker_episode e
      ON e.act_symbol = s.act_symbol
     AND s.ex_date BETWEEN e.start_date AND e.end_date

    JOIN silver.ticker_lineage_membership m
      ON m.ticker_episode_id = e.ticker_episode_id

    JOIN silver.ticker_lineage_master lm
      ON lm.lineage_id = m.lineage_id
),

prices AS (
    SELECT
        lineage_id,
        date,
        act_symbol,
        close,

        LAG(date) OVER (
            PARTITION BY lineage_id
            ORDER BY date
        ) AS previous_date,

        LAG(close) OVER (
            PARTITION BY lineage_id
            ORDER BY date
        ) AS previous_close,

        LAG(act_symbol) OVER (
            PARTITION BY lineage_id
            ORDER BY date
        ) AS previous_ticker

    FROM silver.lineage_ohlcv
)

SELECT
    s.lineage_code,
    s.act_symbol AS split_ticker,
    s.ex_date,
    s.stated_ratio,

    p.previous_date,
    p.previous_ticker,
    p.previous_close,

    p.date AS event_date,
    p.act_symbol AS event_ticker,
    p.close AS event_close,

    CAST(
        p.close * s.stated_ratio
        / NULLIF(p.previous_close, 0) - 1
        AS DOUBLE
    ) AS implied_return

FROM split_events s

LEFT JOIN prices p
  ON p.lineage_id = s.lineage_id
 AND p.date = s.ex_date

ORDER BY s.lineage_code, s.ex_date;
