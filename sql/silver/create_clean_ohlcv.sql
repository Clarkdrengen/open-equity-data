CREATE OR REPLACE TABLE silver.clean_ohlcv AS
SELECT
    o.date,
    o.act_symbol,
    o.open,
    o.high,
    o.low,
    o.close,
    o.volume,
    q.quality_status,
    'dolt' AS source
FROM bronze.ohlcv o
JOIN silver.ohlcv_quality q
  ON q.date = o.date
 AND q.act_symbol = o.act_symbol
WHERE q.quality_status = 'valid_session';
