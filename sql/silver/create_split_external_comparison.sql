DROP TABLE IF EXISTS silver.split_external_comparison;

CREATE TABLE silver.split_external_comparison AS

WITH provider_events AS (
    SELECT
        provider_symbol,
        split_date,
        split_ratio,
        to_factor,
        for_factor,
        observation_id
    FROM bronze.external_split_observation
    WHERE provider = 'EODHD'
),

possible_matches AS (
    SELECT
        c.source_split_row_id,

        c.ticker,
        c.source_ex_date,
        c.stated_ratio,

        c.security_id,
        c.candidate_ticker_episode_id,
        c.episode_mapping_method,

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

        ABS(
            c.stated_ratio - p.split_ratio
        ) AS ratio_difference,

        CASE
            WHEN ABS(c.stated_ratio - p.split_ratio)
                 <= 1e-6 * GREATEST(1.0, ABS(p.split_ratio))
            THEN TRUE
            ELSE FALSE
        END AS ratio_matches,

        CASE
            WHEN c.source_ex_date = p.split_date
            THEN TRUE
            ELSE FALSE
        END AS date_matches

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

    WHERE c.validation_status = 'requires_reconciliation'
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
                ratio_difference,
                provider_split_date
        ) AS match_rank,

        COUNT(*) OVER (
            PARTITION BY source_split_row_id
        ) AS provider_candidates_within_45d,

        SUM(
            CASE WHEN ratio_matches THEN 1 ELSE 0 END
        ) OVER (
            PARTITION BY source_split_row_id
        ) AS same_ratio_candidates_within_45d

    FROM possible_matches
),

best_match AS (
    SELECT *
    FROM ranked
    WHERE match_rank = 1
)

SELECT
    c.source_split_row_id,

    c.security_id,
    c.candidate_ticker_episode_id,
    c.episode_mapping_method,
    c.episode_distance_days,

    c.ticker,
    c.source_ex_date,
    c.stated_ratio,

    c.has_price_on_ex_date,
    c.nearby_same_ratio_duplicate,
    c.large_implied_return,

    b.provider_observation_id,
    b.provider_split_date,
    b.provider_split_ratio,
    b.provider_to_factor,
    b.provider_for_factor,

    b.date_distance_days,
    b.ratio_difference,
    COALESCE(b.date_matches, FALSE) AS date_matches,
    COALESCE(b.ratio_matches, FALSE) AS ratio_matches,

    COALESCE(b.provider_candidates_within_45d, 0)
        AS provider_candidates_within_45d,

    COALESCE(b.same_ratio_candidates_within_45d, 0)
        AS same_ratio_candidates_within_45d,

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
  ON c.source_split_row_id = b.source_split_row_id

WHERE c.validation_status = 'requires_reconciliation';
