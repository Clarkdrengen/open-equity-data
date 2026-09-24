DROP TABLE IF EXISTS silver.security_daily_return_basis;

CREATE TABLE silver.security_daily_return_basis AS

SELECT
    p.security_id,
    p.identity_status,
    p.lineage_id,
    p.lineage_code,
    p.date,
    p.ticker,

    p.open,
    p.high,
    p.low,
    p.close,
    p.volume,

    p.source,
    p.source_symbol,
    p.source_lookup_method,
    p.reconciliation_status,
    p.observation_type,
    p.research_eligible AS price_research_eligible,

    f.daily_split_ratio,
    f.cumulative_split_multiplier,
    f.cumulative_log_split_multiplier,

    p.close * f.cumulative_split_multiplier
        AS split_normalized_close

FROM silver.security_daily_ohlcv_reconciled p

JOIN silver.security_daily_split_factor_reconciled f
  ON f.security_id = p.security_id
 AND f.date = p.date;
