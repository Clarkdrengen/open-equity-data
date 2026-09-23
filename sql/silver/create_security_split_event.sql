DROP TABLE IF EXISTS silver.security_split_event;

CREATE TABLE silver.security_split_event AS

WITH provisional AS (
    SELECT
        security_id,
        ticker,
        validated_ex_date AS split_date,
        validated_ratio AS split_ratio,
        to_factor,
        for_factor,

        'dolt' AS validation_source,
        'dolt_provisional' AS validation_method,

        NULL::VARCHAR AS provider_observation_id,
        1::BIGINT AS source_row_count

    FROM silver.security_split_candidate

    WHERE validation_status = 'provisionally_accepted'
      AND security_id IS NOT NULL
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
        BOOL_OR(date_matches) AS has_exact_date_match

    FROM silver.split_external_comparison

    WHERE provider_observation_id IS NOT NULL
      AND ratio_matches
      AND security_id IS NOT NULL

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
             AND has_exact_date_match
            THEN 'eodhd_duplicate_collapse'

            WHEN source_row_count > 1
             AND NOT has_exact_date_match
            THEN 'eodhd_date_correction_duplicate_collapse'

            WHEN has_exact_date_match
            THEN 'eodhd_exact_confirmation'

            ELSE 'eodhd_date_correction'
        END AS validation_method,

        provider_observation_id,
        source_row_count

    FROM provider_groups
),

combined AS (
    SELECT * FROM provisional
    UNION ALL
    SELECT * FROM provider_validated
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY security_id, split_date
            ORDER BY
                CASE
                    WHEN validation_source = 'eodhd' THEN 1
                    WHEN validation_source = 'dolt' THEN 2
                    ELSE 3
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
