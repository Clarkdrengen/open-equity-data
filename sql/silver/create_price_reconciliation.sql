-- ============================================================
-- Canonical external-price reconciliation
--
-- IMPORTANT:
-- Bronze lineage_id / lineage_code are provenance only.
--
-- Current lineage assignment is resolved entirely in Silver via:
--
--   silver.missing_price_queue
--       -> silver.external_price_resolution_candidate
--       -> silver.external_price_resolution
--
-- Only deterministically resolved observations are admitted here.
-- ============================================================

DROP TABLE IF EXISTS silver.price_reconciliation;

CREATE TABLE silver.price_reconciliation AS

SELECT
    r.current_lineage_id AS lineage_id,
    r.current_lineage_code AS lineage_code,
    r.session_date AS date,

    r.candidate_ticker AS ticker,

    r.open,
    r.high,
    r.low,
    r.close,
    r.provider_volume AS volume,

    'eodhd' AS source,
    r.provider_symbol AS source_symbol,
    r.lookup_method AS source_lookup_method,

    CASE
        WHEN r.provider_volume = 0
         AND r.open = r.high
         AND r.high = r.low
         AND r.low = r.close
        THEN 'external_zero_volume_observation'

        WHEN r.lookup_method =
             'lineage_latest_ticker_fallback'
        THEN 'accepted_external_fill_lineage_fallback'

        ELSE 'accepted_external_fill'
    END AS reconciliation_status,

    CASE
        WHEN r.provider_volume = 0
         AND r.open = r.high
         AND r.high = r.low
         AND r.low = r.close
        THEN 'external_zero_volume_bar'

        ELSE 'external_traded_bar'
    END AS observation_type,

    CASE
        WHEN r.provider_volume = 0
         AND r.open = r.high
         AND r.high = r.low
         AND r.low = r.close
        THEN FALSE

        ELSE TRUE
    END AS research_eligible,

    r.provider_adjusted_close,
    r.retrieved_at,

    -- Explicit provenance. These fields are descriptive only.
    r.observation_id AS bronze_observation_id,
    r.request_id AS bronze_request_id,
    r.bronze_stored_lineage_id,
    r.bronze_stored_lineage_code

FROM silver.external_price_resolution r

WHERE r.resolution_status = 'resolved';
