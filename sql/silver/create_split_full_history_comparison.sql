DROP TABLE IF EXISTS silver.split_full_history_comparison;

CREATE TABLE silver.split_full_history_comparison AS

WITH provider_events AS (
    SELECT
        provider_symbol,
        split_date,
        split_ratio,
        to_factor,
        for_factor,
        observation_id
    FROM bronze.external_split_full_history_observation
    WHERE provider = 'EODHD'
),

possible_matches AS (
    SELECT
        c.source_split_row_id,
        c.security_id,
        c.candidate_ticker_episode_id,
        c.episode_mapping_method,

        c.ticker,
        c.source_ex_date,
        c.stated_ratio,

        p.observation_id AS provider_observation_id,
        p.split_date AS provider_split_date,
        p.split_ratio AS provider_split_ratio,
        p.to_factor AS provider_to_factor,
        p.for_factor AS provider_for_factor,

        ABS(
            date_diff(
                'day',
                c.source_ex_date,
                p.split_date
            )
        ) AS date_distance_days,

        CASE
            WHEN c.stated_ratio IS NULL
              OR p.split_ratio IS NULL
            THEN NULL
            ELSE ABS(c.stated_ratio - p.split_ratio)
        END AS ratio_difference,

        CASE
            WHEN c.stated_ratio IS NULL
            THEN FALSE
            WHEN ABS(c.stated_ratio - p.split_ratio)
                 <= 1e-6 * GREATEST(1.0, ABS(p.split_ratio))
            THEN TRUE
            ELSE FALSE
        END AS ratio_matches,

        (c.source_ex_date = p.split_date) AS date_matches

    FROM silver.security_split_candidate c

    JOIN provider_events p
      ON p.provider_symbol = c.ticker || '.US'
     AND ABS(
            date_diff(
                'day',
                c.source_ex_date,
                p.split_date
            )
         ) <= 45
),

ranked AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            PARTITION BY source_split_row_id
            ORDER BY
                CASE
                    WHEN date_matches AND ratio_matches THEN 1
                    WHEN ratio_matches THEN 2
                    WHEN date_matches THEN 3
                    ELSE 4
                END,
                date_distance_days,
                ratio_difference NULLS LAST,
                provider_split_date
        ) AS match_rank

    FROM possible_matches
),

best_match AS (
    SELECT *
    FROM ranked
    WHERE match_rank = 1
)

SELECT
    c.*,

    b.provider_observation_id,
    b.provider_split_date,
    b.provider_split_ratio,
    b.provider_to_factor,
    b.provider_for_factor,
    b.date_distance_days,
    b.ratio_difference,

    COALESCE(b.date_matches, FALSE) AS date_matches,
    COALESCE(b.ratio_matches, FALSE) AS ratio_matches,

    CASE
        WHEN b.provider_observation_id IS NULL
        THEN 'no_provider_match_within_45d'

        WHEN b.date_matches
         AND b.ratio_matches
        THEN 'exact_date_exact_ratio'

        WHEN b.ratio_matches
         AND NOT b.date_matches
        THEN 'nearby_date_exact_ratio'

        WHEN b.date_matches
         AND NOT b.ratio_matches
        THEN 'exact_date_ratio_conflict'

        ELSE 'nearby_date_ratio_conflict'
    END AS comparison_status

FROM silver.security_split_candidate c

LEFT JOIN best_match b
  ON c.source_split_row_id = b.source_split_row_id;
