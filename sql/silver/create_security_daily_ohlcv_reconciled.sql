DROP TABLE IF EXISTS silver.security_daily_ohlcv_reconciled;

CREATE TABLE silver.security_daily_ohlcv_reconciled AS

SELECT
    p.security_id,
    p.identity_status,
    p.lineage_id,
    p.lineage_code,
    p.date,
    p.ticker,

    COALESCE(c.open, p.open) AS open,
    COALESCE(c.high, p.high) AS high,
    COALESCE(c.low, p.low) AS low,
    COALESCE(c.close, p.close) AS close,
    COALESCE(c.volume, p.volume) AS volume,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN 'eodhd'
        ELSE p.source
    END AS source,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN c.provider_symbol
        ELSE p.source_symbol
    END AS source_symbol,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN 'automatic_high_confidence_price_correction'
        ELSE p.source_lookup_method
    END AS source_lookup_method,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN 'automatic_price_correction'
        ELSE p.reconciliation_status
    END AS reconciliation_status,

    p.observation_type,
    p.research_eligible

FROM silver.security_daily_ohlcv p

LEFT JOIN silver.automatic_price_correction c
  ON c.security_id = p.security_id
 AND c.correction_date = p.date;
