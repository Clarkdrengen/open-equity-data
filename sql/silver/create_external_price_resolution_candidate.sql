-- ============================================================
-- Candidate resolution of immutable Bronze external-price
-- evidence onto the CURRENT Silver lineage model.
--
-- Bronze lineage_id / lineage_code are provenance only.
-- They have NO authority over current identity assignment.
--
-- Current identity comes from silver.missing_price_queue.
-- ============================================================

DROP TABLE IF EXISTS silver.external_price_resolution_candidate;

CREATE TABLE silver.external_price_resolution_candidate AS

WITH candidates AS (
    SELECT
        -- Current Silver identity
        q.lineage_id
            AS current_lineage_id,

        q.lineage_code
            AS current_lineage_code,

        q.session_date,
        q.candidate_ticker,
        q.gap_type,

        -- Immutable Bronze evidence / provenance
        o.observation_id,
        o.request_id,
        o.provider,
        o.provider_symbol,

        o.lineage_id
            AS bronze_stored_lineage_id,

        o.lineage_code
            AS bronze_stored_lineage_code,

        o.historical_ticker,
        o.lookup_method,

        o.open,
        o.high,
        o.low,
        o.close,
        o.provider_adjusted_close,
        o.provider_volume,

        o.retrieved_at,
        o.raw_payload_json,

        -- Prefer an observation requested using the historical
        -- ticker itself. Fallback-to-latest-ticker observations
        -- remain legitimate secondary evidence.
        CASE
            WHEN o.lookup_method =
                 'historical_ticker_lookup'
            THEN 1

            WHEN o.lookup_method =
                 'lineage_latest_ticker_fallback'
            THEN 2

            ELSE 9
        END AS match_priority,

        (
            UPPER(o.provider_symbol)
            =
            UPPER(q.candidate_ticker || '.US')
        ) AS provider_symbol_matches_candidate,

        -- Economic identity of the observation independent of
        -- request ID / old lineage assignment.
        md5(
            COALESCE(CAST(o.open AS VARCHAR), '<NULL>') || '|' ||
            COALESCE(CAST(o.high AS VARCHAR), '<NULL>') || '|' ||
            COALESCE(CAST(o.low AS VARCHAR), '<NULL>') || '|' ||
            COALESCE(CAST(o.close AS VARCHAR), '<NULL>') || '|' ||
            COALESCE(
                CAST(o.provider_adjusted_close AS VARCHAR),
                '<NULL>'
            ) || '|' ||
            COALESCE(
                CAST(o.provider_volume AS VARCHAR),
                '<NULL>'
            )
        ) AS economic_fingerprint

    FROM silver.missing_price_queue q

    JOIN bronze.external_price_observation o
      ON o.provider = 'EODHD'
     AND o.session_date = q.session_date
     AND UPPER(o.historical_ticker)
         = UPPER(q.candidate_ticker)

    WHERE q.candidate_ticker IS NOT NULL
),

with_match_count AS (
    SELECT
        *,

        -- If one immutable Bronze observation can be attached to
        -- more than one CURRENT lineage/date requirement, do not
        -- silently choose one.
        COUNT(*) OVER (
            PARTITION BY observation_id
        ) AS current_match_count

    FROM candidates
)

SELECT *
FROM with_match_count;
