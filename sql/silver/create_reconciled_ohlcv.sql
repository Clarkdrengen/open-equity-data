DROP TABLE IF EXISTS silver.reconciled_ohlcv;

CREATE TABLE silver.reconciled_ohlcv AS

-- Native Dolt observations
SELECT
    l.lineage_id,
    l.lineage_code,
    l.date,
    l.act_symbol AS ticker,

    CAST(l.open AS DOUBLE) AS open,
    CAST(l.high AS DOUBLE) AS high,
    CAST(l.low AS DOUBLE) AS low,
    CAST(l.close AS DOUBLE) AS close,
    CAST(l.volume AS BIGINT) AS volume,

    'dolt' AS source,
    l.act_symbol AS source_symbol,
    'native' AS source_lookup_method,

    'native' AS reconciliation_status,
    'native' AS observation_type,
    TRUE AS research_eligible

FROM silver.lineage_ohlcv l

UNION ALL

-- External observations for sessions absent from Dolt
SELECT
    r.lineage_id,
    r.lineage_code,
    r.date,
    r.ticker,

    r.open,
    r.high,
    r.low,
    r.close,
    r.volume,

    r.source,
    r.source_symbol,
    r.source_lookup_method,

    r.reconciliation_status,
    r.observation_type,
    r.research_eligible

FROM silver.price_reconciliation r

WHERE NOT EXISTS (
    SELECT 1
    FROM silver.lineage_ohlcv l
    WHERE l.lineage_id = r.lineage_id
      AND l.date = r.date
);
