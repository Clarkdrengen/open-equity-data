DROP TABLE IF EXISTS silver.security_daily_ohlcv;

-- This derived candidate is empty until a dated EODHD bulk response has been
-- archived in Bronze and explicitly processed by recover_eodhd_bulk_price_gaps.
CREATE TABLE IF NOT EXISTS silver.eodhd_bulk_missing_price_candidate (
    security_id BIGINT, identity_status VARCHAR, lineage_id BIGINT,
    lineage_code VARCHAR, date DATE, ticker VARCHAR, open DOUBLE,
    high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT,
    response_sha256 VARCHAR, before_close DOUBLE, after_close DOUBLE,
    candidate_status VARCHAR
);

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
 AND s.identity_status = 'singleton_episode'

UNION ALL

-- Source-backed exact-session recovery; native Dolt rows remain authoritative.
SELECT
    c.security_id, c.identity_status, c.lineage_id, c.lineage_code,
    c.date, c.ticker, c.open, c.high, c.low, c.close, c.volume,
    'eodhd' AS source,
    c.ticker || '.US' AS source_symbol,
    'bulk_exact_ticker_adjacent_security' AS source_lookup_method,
    'bulk_missing_dolt_session' AS reconciliation_status,
    'external_recovered' AS observation_type,
    TRUE AS research_eligible
FROM silver.eodhd_bulk_missing_price_candidate c
WHERE c.candidate_status = 'candidate_usable';
