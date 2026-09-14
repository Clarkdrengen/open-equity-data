-- Initial diagnostic for validating reported stock splits
-- against observed price discontinuities.

WITH prices AS (
    SELECT
        date,
        act_symbol,
        close,
        LAG(close) OVER (
            PARTITION BY act_symbol
            ORDER BY date
        ) AS previous_close
    FROM bronze.ohlcv
)
SELECT
    s.act_symbol,
    s.ex_date,
    s.to_factor,
    s.for_factor,
    CAST(s.to_factor / s.for_factor AS DOUBLE) AS stated_ratio,
    p.previous_close,
    p.close,
    CAST(p.close / p.previous_close AS DOUBLE) AS raw_price_ratio,
    CAST(
        p.close * (s.to_factor / s.for_factor)
        / p.previous_close - 1
        AS DOUBLE
    ) AS implied_return
FROM bronze.split AS s
LEFT JOIN prices AS p
    ON p.act_symbol = s.act_symbol
   AND p.date = s.ex_date
ORDER BY s.ex_date DESC, s.act_symbol;
