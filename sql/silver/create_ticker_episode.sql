-- ============================================================
-- Identity-aware ticker episodes
--
-- PRINCIPLE
-- ---------
-- Gaps in observed trading NEVER create security identity breaks.
--
-- Episodes are split only at explicit validated identity events:
-- currently, same-security ticker transitions recorded in
-- silver.ticker_transition_evidence.
--
-- Example:
--   LBTYB sparse trading -> one episode
--
--   FB -> META on 2022-06-09:
--       FB observations before the transition belong to the
--       predecessor issue.
--       Any later reuse of FB is a separate ticker episode.
--
--   Historical META observations before the transition similarly
--       remain separate from post-transition META.
--
-- Observation gaps are retained only as diagnostics.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.ticker_episode AS

WITH

-- ------------------------------------------------------------
-- 1. Explicit identity-event boundaries
--
-- A validated transition A -> B at date d creates a boundary for
-- BOTH A and B.
--
-- This allows:
--   - later reuse of A to become a new episode;
--   - earlier use of B to remain separate from the new security.
-- ------------------------------------------------------------

boundaries AS (
    SELECT DISTINCT
        from_ticker AS act_symbol,
        effective_date
    FROM silver.ticker_transition_evidence
    WHERE same_security = TRUE
      AND from_ticker IS NOT NULL
      AND effective_date IS NOT NULL

    UNION

    SELECT DISTINCT
        to_ticker AS act_symbol,
        effective_date
    FROM silver.ticker_transition_evidence
    WHERE same_security = TRUE
      AND to_ticker IS NOT NULL
      AND effective_date IS NOT NULL
),

-- ------------------------------------------------------------
-- 2. Assign every OHLCV observation to the interval determined
--    by explicit identity boundaries.
--
-- No trading-gap rule appears here.
-- ------------------------------------------------------------

assigned AS (
    SELECT
        o.act_symbol,
        o.date,

        1 + COUNT(b.effective_date)
            FILTER (
                WHERE b.effective_date <= o.date
            ) AS episode_number

    FROM silver.clean_ohlcv o

    LEFT JOIN boundaries b
      ON b.act_symbol = o.act_symbol

    GROUP BY
        o.act_symbol,
        o.date
),

-- ------------------------------------------------------------
-- 3. Gap diagnostics *within* the identity-aware episode.
-- ------------------------------------------------------------

ordered AS (
    SELECT
        act_symbol,
        episode_number,
        date,

        LAG(date) OVER (
            PARTITION BY
                act_symbol,
                episode_number
            ORDER BY date
        ) AS previous_date

    FROM assigned
),

episode_stats AS (
    SELECT
        act_symbol,
        episode_number,

        MIN(date) AS start_date,
        MAX(date) AS end_date,

        COUNT(*) AS n_observations,

        MAX(
            CASE
                WHEN previous_date IS NOT NULL
                THEN DATE_DIFF(
                    'day',
                    previous_date,
                    date
                )
            END
        ) AS max_internal_gap_days,

        COUNT(*) FILTER (
            WHERE previous_date IS NOT NULL
              AND DATE_DIFF(
                    'day',
                    previous_date,
                    date
                  ) > 7
        ) AS gaps_over_7_days,

        COUNT(*) FILTER (
            WHERE previous_date IS NOT NULL
              AND DATE_DIFF(
                    'day',
                    previous_date,
                    date
                  ) > 30
        ) AS gaps_over_30_days

    FROM ordered

    GROUP BY
        act_symbol,
        episode_number
)

SELECT
    act_symbol
        || '_E'
        || LPAD(
            CAST(episode_number AS VARCHAR),
            3,
            '0'
        )
        AS ticker_episode_id,

    act_symbol,
    episode_number,

    start_date,
    end_date,
    n_observations,

    max_internal_gap_days,
    gaps_over_7_days,
    gaps_over_30_days

FROM episode_stats

ORDER BY
    act_symbol,
    episode_number;
