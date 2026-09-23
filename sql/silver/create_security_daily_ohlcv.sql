DROP TABLE IF EXISTS silver.security_daily_ohlcv;

CREATE TABLE silver.security_daily_ohlcv AS

-- ------------------------------------------------------------
-- Validated multi-episode securities.
-- Use the reconciled lineage series so externally recovered
-- observations and their provenance are retained.
-- ------------------------------------------------------------

SELECT
    s.security_id,
    s.identity_status,
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

FROM silver.reconciled_ohlcv r

JOIN silver.security_master s
  ON s.lineage_id = r.lineage_id
 AND s.identity_status = 'validated_lineage'


UNION ALL


-- ------------------------------------------------------------
-- Singleton securities.
-- These have no validated cross-episode identity relationship,
-- so each ticker episode remains its own security.
-- ------------------------------------------------------------

SELECT
    sem.security_id,
    s.identity_status,
    NULL::BIGINT AS lineage_id,
    NULL::VARCHAR AS lineage_code,

    o.date,
    o.act_symbol AS ticker,

    CAST(o.open AS DOUBLE) AS open,
    CAST(o.high AS DOUBLE) AS high,
    CAST(o.low AS DOUBLE) AS low,
    CAST(o.close AS DOUBLE) AS close,
    CAST(o.volume AS BIGINT) AS volume,

    'dolt' AS source,
    o.act_symbol AS source_symbol,
    'native' AS source_lookup_method,
    'native' AS reconciliation_status,
    'native' AS observation_type,
    TRUE AS research_eligible

FROM silver.clean_ohlcv o

JOIN silver.ticker_episode e
  ON e.act_symbol = o.act_symbol
 AND o.date BETWEEN e.start_date AND e.end_date

JOIN silver.security_episode_membership sem
  ON sem.ticker_episode_id = e.ticker_episode_id

JOIN silver.security_master s
  ON s.security_id = sem.security_id
 AND s.identity_status = 'singleton_episode';
