DROP TABLE IF EXISTS silver.security_split_event;

CREATE TABLE silver.security_split_event AS

WITH secure_provider_matches AS (
    SELECT *
    FROM silver.split_full_history_comparison
    WHERE provider_observation_id IS NOT NULL
      AND security_id IS NOT NULL
      AND (
            ratio_matches
            OR date_matches
          )
),

provider_groups AS (
    SELECT
        provider_observation_id,

        ANY_VALUE(security_id) AS security_id,
        ANY_VALUE(ticker) AS ticker,

        ANY_VALUE(provider_split_date) AS split_date,
        ANY_VALUE(provider_split_ratio) AS split_ratio,
        ANY_VALUE(provider_to_factor) AS to_factor,
        ANY_VALUE(provider_for_factor) AS for_factor,

        COUNT(*) AS source_row_count,

        BOOL_OR(date_matches) AS has_exact_date_match,
        BOOL_OR(ratio_matches) AS has_ratio_match,
        BOOL_OR(date_matches AND ratio_matches)
            AS has_exact_confirmation,
        BOOL_OR(date_matches AND NOT ratio_matches)
            AS has_ratio_correction_case

    FROM secure_provider_matches

    GROUP BY provider_observation_id

    HAVING COUNT(DISTINCT security_id) = 1
),

provider_validated AS (
    SELECT
        security_id,
        ticker,
        split_date,
        split_ratio,
        to_factor,
        for_factor,

        'eodhd' AS validation_source,

        CASE
            WHEN source_row_count > 1
             AND has_exact_confirmation
            THEN 'eodhd_duplicate_collapse'

            WHEN source_row_count > 1
             AND has_ratio_match
             AND NOT has_exact_date_match
            THEN 'eodhd_date_correction_duplicate_collapse'

            WHEN has_ratio_correction_case
            THEN 'eodhd_ratio_correction'

            WHEN has_exact_confirmation
            THEN 'eodhd_exact_confirmation'

            WHEN has_ratio_match
            THEN 'eodhd_date_correction'

            ELSE 'eodhd_validated'
        END AS validation_method,

        provider_observation_id,
        source_row_count

    FROM provider_groups
),

-- Retain a Dolt event only where:
--   1. the original audit considered it clean;
--   2. it has a trusted security mapping;
--   3. EODHD supplied no nearby split event at all.
--
-- If EODHD supplied a nearby event but both its date and ratio conflict,
-- the event remains unresolved rather than silently reverting to Dolt.
dolt_only AS (
    SELECT
        c.security_id,
        c.ticker,
        c.source_ex_date AS split_date,
        c.stated_ratio AS split_ratio,
        c.to_factor,
        c.for_factor,

        'dolt' AS validation_source,
        'dolt_provisional_no_eodhd_match' AS validation_method,

        NULL::VARCHAR AS provider_observation_id,
        1::BIGINT AS source_row_count

    FROM silver.split_full_history_comparison c

    WHERE c.validation_status = 'provisionally_accepted'
      AND c.security_id IS NOT NULL
      AND c.comparison_status = 'no_provider_match_within_45d'
      AND c.stated_ratio IS NOT NULL
      AND c.stated_ratio > 0
),

combined AS (
    SELECT * FROM provider_validated
    UNION ALL
    SELECT * FROM dolt_only
),

-- Final safeguard. If two sources somehow produce the same
-- security/date, EODHD has precedence.
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY security_id, split_date
            ORDER BY
                CASE
                    WHEN validation_source = 'eodhd' THEN 1
                    ELSE 2
                END,
                provider_observation_id NULLS LAST
        ) AS rn
    FROM combined
)

SELECT
    security_id,
    ticker,
    split_date,
    split_ratio,
    to_factor,
    for_factor,
    validation_source,
    validation_method,
    provider_observation_id,
    source_row_count

FROM ranked
WHERE rn = 1;
