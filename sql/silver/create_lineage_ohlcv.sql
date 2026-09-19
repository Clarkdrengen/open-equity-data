CREATE OR REPLACE TABLE silver.lineage_ohlcv AS
SELECT
    m.lineage_id,
    lm.lineage_code,
    m.ticker_episode_id,
    e.act_symbol,
    o.date,
    o.open,
    o.high,
    o.low,
    o.close,
    o.volume
FROM silver.ticker_lineage_membership m

JOIN silver.ticker_lineage_master lm
  ON lm.lineage_id = m.lineage_id

JOIN silver.ticker_episode e
  ON e.ticker_episode_id = m.ticker_episode_id

JOIN silver.clean_ohlcv o
  ON o.act_symbol = e.act_symbol
 AND o.date BETWEEN e.start_date AND e.end_date;
