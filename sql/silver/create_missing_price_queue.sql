CREATE OR REPLACE TABLE silver.missing_price_queue AS

WITH missing AS (
    SELECT
        lineage_id,
        lineage_code,
        session_date
    FROM silver.daily_coverage
    WHERE NOT observation_present
),

context AS (
    SELECT
        m.*,

        (
            SELECT MAX(o.date)
            FROM silver.lineage_ohlcv o
            WHERE o.lineage_id = m.lineage_id
              AND o.date < m.session_date
        ) AS previous_observation_date,

        (
            SELECT MIN(o.date)
            FROM silver.lineage_ohlcv o
            WHERE o.lineage_id = m.lineage_id
              AND o.date > m.session_date
        ) AS next_observation_date

    FROM missing m
),

enriched AS (
    SELECT
        c.*,

        p.ticker_episode_id AS previous_episode_id,
        p.act_symbol AS previous_ticker,
        p.close AS previous_close,

        n.ticker_episode_id AS next_episode_id,
        n.act_symbol AS next_ticker,
        n.close AS next_close

    FROM context c

    LEFT JOIN silver.lineage_ohlcv p
      ON p.lineage_id = c.lineage_id
     AND p.date = c.previous_observation_date

    LEFT JOIN silver.lineage_ohlcv n
      ON n.lineage_id = c.lineage_id
     AND n.date = c.next_observation_date
)

SELECT
    e.lineage_id,
    e.lineage_code,
    e.session_date,

    e.previous_observation_date,
    e.previous_episode_id,
    e.previous_ticker,
    e.previous_close,

    e.next_observation_date,
    e.next_episode_id,
    e.next_ticker,
    e.next_close,

    t.effective_date AS transition_effective_date,

    CASE
        WHEN e.previous_ticker = e.next_ticker
            THEN e.previous_ticker

        WHEN t.transition_id IS NOT NULL
         AND e.session_date < t.effective_date
            THEN t.from_ticker

        WHEN t.transition_id IS NOT NULL
         AND e.session_date >= t.effective_date
            THEN t.to_ticker

        ELSE NULL
    END AS candidate_ticker,

    CASE
        WHEN e.previous_ticker = e.next_ticker
            THEN 'same_ticker_gap'

        WHEN t.transition_id IS NOT NULL
            THEN 'validated_transition_gap'

        ELSE 'unresolved_cross_ticker_gap'
    END AS gap_type,

    sc.is_early_close,
    sc.continuity_coverage_pct,
    sc.coverage_percentile,
    sc.coverage_diagnostic,

    'unresolved' AS reconciliation_status

FROM enriched e

LEFT JOIN silver.ticker_transition t
  ON t.from_episode_id = e.previous_episode_id
 AND t.to_episode_id = e.next_episode_id
 AND t.same_security = TRUE

LEFT JOIN silver.session_coverage_ranked sc
  ON sc.session_date = e.session_date

ORDER BY
    e.lineage_id,
    e.session_date;
