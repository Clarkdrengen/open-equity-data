DROP TABLE IF EXISTS silver.extreme_return_price_comparison;

CREATE TABLE silver.extreme_return_price_comparison AS

WITH extreme AS (
    SELECT
        r.security_id,
        r.ticker,
        r.date,
        r.previous_date,

        r.previous_close AS dolt_previous_close,
        r.close AS dolt_close,

        r.price_return AS dolt_price_return,
        r.gross_total_return AS dolt_gross_total_return,

        r.daily_split_ratio,
        r.dividend_previous_share_basis,
        r.source AS dolt_source
    FROM silver.security_daily_return r
    WHERE r.research_eligible
      AND ABS(r.gross_total_return) > 1.0
),

request_status AS (
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
        FROM bronze.external_price_validation_request
        WHERE provider = 'EODHD'
    )
    WHERE rn = 1
),

joined AS (
    SELECT
        e.*,

        rs.provider_symbol,
        rs.status_code AS provider_request_status_code,
        rs.response_row_count AS provider_response_row_count,
        rs.error_text AS provider_request_error,

        p.date AS provider_previous_date,
        p.open AS provider_previous_open,
        p.high AS provider_previous_high,
        p.low AS provider_previous_low,
        p.close AS provider_previous_close,
        p.adjusted_close AS provider_previous_adjusted_close,
        p.volume AS provider_previous_volume,

        c.date AS provider_current_date,
        c.open AS provider_current_open,
        c.high AS provider_current_high,
        c.low AS provider_current_low,
        c.close AS provider_current_close,
        c.adjusted_close AS provider_current_adjusted_close,
        c.volume AS provider_current_volume

    FROM extreme e

    LEFT JOIN request_status rs
      ON rs.ticker = e.ticker

    LEFT JOIN bronze.external_price_validation_observation p
      ON p.provider = 'EODHD'
     AND p.provider_symbol = rs.provider_symbol
     AND p.date = e.previous_date

    LEFT JOIN bronze.external_price_validation_observation c
      ON c.provider = 'EODHD'
     AND c.provider_symbol = rs.provider_symbol
     AND c.date = e.date
),

metrics AS (
    SELECT
        *,

        CASE
            WHEN provider_previous_close > 0
             AND provider_current_close IS NOT NULL
            THEN provider_current_close / provider_previous_close - 1.0
            ELSE NULL
        END AS provider_raw_return,

        CASE
            WHEN provider_previous_adjusted_close > 0
             AND provider_current_adjusted_close IS NOT NULL
            THEN provider_current_adjusted_close
                 / provider_previous_adjusted_close - 1.0
            ELSE NULL
        END AS provider_adjusted_return,

        CASE
            WHEN dolt_previous_close > 0
             AND provider_previous_close IS NOT NULL
            THEN provider_previous_close / dolt_previous_close
            ELSE NULL
        END AS provider_to_dolt_previous_close_ratio,

        CASE
            WHEN dolt_close > 0
             AND provider_current_close IS NOT NULL
            THEN provider_current_close / dolt_close
            ELSE NULL
        END AS provider_to_dolt_current_close_ratio

    FROM joined
)

SELECT
    *,

    CASE
        WHEN provider_request_status_code IS NULL
        THEN 'no_provider_request'

        WHEN provider_request_status_code = 404
        THEN 'provider_symbol_not_found'

        WHEN provider_request_status_code <> 200
        THEN 'provider_request_failed'

        WHEN provider_previous_close IS NULL
          OR provider_current_close IS NULL
        THEN 'provider_price_pair_missing'

        WHEN ABS(provider_raw_return) > 1.0
        THEN 'provider_raw_also_extreme'

        ELSE 'provider_raw_not_extreme'
    END AS comparison_status,

    CASE
        WHEN provider_raw_return IS NULL
        THEN NULL
        ELSE dolt_price_return - provider_raw_return
    END AS raw_return_difference,

    CASE
        WHEN provider_adjusted_return IS NULL
        THEN NULL
        ELSE dolt_gross_total_return - provider_adjusted_return
    END AS adjusted_return_difference

FROM metrics;
