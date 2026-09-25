-- ============================================================
-- Resolve cached Bronze external-price evidence onto CURRENT
-- Silver lineage identity.
--
-- Resolution policy:
--   1. use current missing_price_queue identity;
--   2. prefer historical-ticker lookup over latest-ticker fallback;
--   3. require economic agreement among candidates at the best
--      available priority;
--   4. reject a Bronze observation that maps to multiple current
--      lineage/date requirements;
--   5. preserve unresolved cases explicitly.
-- ============================================================

DROP TABLE IF EXISTS silver.external_price_resolution;

CREATE TABLE silver.external_price_resolution AS

WITH best_priority AS (
    SELECT
        current_lineage_id,
        session_date,
        MIN(match_priority)
            AS best_match_priority

    FROM silver.external_price_resolution_candidate

    GROUP BY
        current_lineage_id,
        session_date
),

best_candidates AS (
    SELECT c.*

    FROM silver.external_price_resolution_candidate c

    JOIN best_priority p
      ON p.current_lineage_id =
         c.current_lineage_id
     AND p.session_date =
         c.session_date
     AND p.best_match_priority =
         c.match_priority
),

candidate_stats AS (
    SELECT
        current_lineage_id,
        session_date,

        COUNT(*) AS candidate_count,

        COUNT(DISTINCT observation_id)
            AS distinct_observation_count,

        COUNT(DISTINCT economic_fingerprint)
            AS economic_variant_count,

        MAX(current_match_count)
            AS max_current_match_count

    FROM best_candidates

    GROUP BY
        current_lineage_id,
        session_date
),

ranked AS (
    SELECT
        c.*,

        ROW_NUMBER() OVER (
            PARTITION BY
                c.current_lineage_id,
                c.session_date

            ORDER BY
                c.provider_symbol_matches_candidate DESC,
                c.retrieved_at DESC,
                c.observation_id
        ) AS selection_rank

    FROM best_candidates c
),

selected AS (
    SELECT *
    FROM ranked
    WHERE selection_rank = 1
),

all_candidate_stats AS (
    SELECT
        current_lineage_id,
        session_date,
        COUNT(*) AS all_candidate_count

    FROM silver.external_price_resolution_candidate

    GROUP BY
        current_lineage_id,
        session_date
)

SELECT
    -- Current Silver requirement / identity
    q.lineage_id
        AS current_lineage_id,

    q.lineage_code
        AS current_lineage_code,

    q.session_date,
    q.candidate_ticker,
    q.gap_type,

    -- Selected immutable Bronze observation
    s.observation_id,
    s.request_id,
    s.provider,
    s.provider_symbol,

    s.bronze_stored_lineage_id,
    s.bronze_stored_lineage_code,

    s.historical_ticker,
    s.lookup_method,

    s.open,
    s.high,
    s.low,
    s.close,
    s.provider_adjusted_close,
    s.provider_volume,

    s.retrieved_at,

    s.match_priority,

    COALESCE(a.all_candidate_count, 0)
        AS all_candidate_count,

    COALESCE(cs.candidate_count, 0)
        AS best_priority_candidate_count,

    COALESCE(cs.distinct_observation_count, 0)
        AS distinct_observation_count,

    COALESCE(cs.economic_variant_count, 0)
        AS economic_variant_count,

    COALESCE(cs.max_current_match_count, 0)
        AS max_current_match_count,

    CASE
        WHEN q.candidate_ticker IS NULL
        THEN 'no_candidate_ticker'

        WHEN cs.current_lineage_id IS NULL
        THEN 'no_cached_observation'

        WHEN cs.max_current_match_count > 1
        THEN
            'ambiguous_observation_maps_multiple_current_lineages'

        WHEN cs.economic_variant_count > 1
        THEN 'conflicting_cached_observations'

        ELSE 'resolved'
    END AS resolution_status

FROM silver.missing_price_queue q

LEFT JOIN candidate_stats cs
  ON cs.current_lineage_id = q.lineage_id
 AND cs.session_date = q.session_date

LEFT JOIN all_candidate_stats a
  ON a.current_lineage_id = q.lineage_id
 AND a.session_date = q.session_date

LEFT JOIN selected s
  ON s.current_lineage_id = q.lineage_id
 AND s.session_date = q.session_date;
