DROP TABLE IF EXISTS silver.corporate_action_candidate_split_comparison;

CREATE TABLE silver.corporate_action_candidate_split_comparison AS

WITH candidates AS (
    SELECT
        security_id,
        ticker,
        date,
        dolt_price_return,
        dolt_gross_total_return,
        provider_raw_return,
        provider_adjusted_return,
        daily_split_ratio,
        dividend_previous_share_basis
    FROM silver.extreme_return_diagnostic
    WHERE diagnostic_class = 'corporate_action_candidate'
),

req AS (
    SELECT *
    FROM (
        SELECT
            ticker,
            provider_symbol,
            status_code,
            response_row_count,
            error_text,
            retrieved_at,
            ROW_NUMBER() OVER (
                PARTITION BY ticker
                ORDER BY retrieved_at DESC
            ) AS rn
        FROM bronze.external_split_candidate_validation_request
        WHERE provider = 'EODHD'
    )
    WHERE rn = 1
),

nearest AS (
    SELECT
        c.*,
        r.provider_symbol,
        r.status_code,
        r.response_row_count,
        r.error_text,
        s.ex_date AS provider_split_date,
        s.split_ratio AS provider_split_ratio,
        ABS(date_diff('day', c.date, s.ex_date)) AS day_distance,
        ROW_NUMBER() OVER (
            PARTITION BY c.security_id, c.ticker, c.date
            ORDER BY
                ABS(date_diff('day', c.date, s.ex_date)),
                s.ex_date
        ) AS rn
    FROM candidates c
    LEFT JOIN req r
      ON r.ticker = c.ticker
    LEFT JOIN bronze.external_split_candidate_validation_observation s
      ON s.provider = 'EODHD'
     AND s.provider_symbol = r.provider_symbol
     AND s.ex_date BETWEEN c.date - INTERVAL 45 DAY
                       AND c.date + INTERVAL 45 DAY
),

best AS (
    SELECT *
    FROM nearest
    WHERE rn = 1
)

SELECT
    security_id,
    ticker,
    date,
    dolt_price_return,
    dolt_gross_total_return,
    provider_raw_return,
    provider_adjusted_return,
    daily_split_ratio,
    dividend_previous_share_basis,

    provider_symbol,
    status_code AS provider_request_status_code,
    response_row_count AS provider_response_row_count,
    error_text AS provider_request_error,

    provider_split_date,
    provider_split_ratio,
    day_distance,

    CASE
        WHEN status_code IS NULL
        THEN 'no_provider_request'

        WHEN status_code = 404
        THEN 'provider_symbol_not_found'

        WHEN status_code <> 200
        THEN 'provider_request_failed'

        WHEN provider_split_date IS NULL
        THEN 'no_provider_split_within_45d'

        WHEN provider_split_date = date
         AND ABS(provider_split_ratio - daily_split_ratio) < 1e-8
        THEN 'exact_date_exact_ratio_already_present'

        WHEN provider_split_date = date
         AND ABS(provider_split_ratio - daily_split_ratio) >= 1e-8
        THEN 'exact_date_ratio_conflict'

        WHEN provider_split_date <> date
         AND ABS(provider_split_ratio - daily_split_ratio) < 1e-8
        THEN 'nearby_date_exact_ratio'

        WHEN provider_split_date <> date
        THEN 'nearby_date_ratio_conflict'

        ELSE 'other'
    END AS split_comparison_status

FROM best;
