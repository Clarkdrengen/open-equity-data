DROP TABLE IF EXISTS silver.unresolved_symbol_search_resolution;

CREATE TABLE silver.unresolved_symbol_search_resolution AS

WITH parsed AS (
    SELECT
        query_ticker,
        result_rank,
        result_code,
        result_exchange,
        result_name,
        result_type,
        result_country,
        result_currency,

        CASE
            WHEN UPPER(result_code) LIKE '%.US'
            THEN regexp_replace(
                UPPER(result_code),
                '\\.US$',
                ''
            )
            ELSE UPPER(result_code)
        END AS parsed_ticker_body,

        UPPER(query_ticker) AS query_ticker_upper,

        regexp_replace(
            CASE
                WHEN UPPER(result_code) LIKE '%.US'
                THEN regexp_replace(
                    UPPER(result_code),
                    '\\.US$',
                    ''
                )
                ELSE UPPER(result_code)
            END,
            '[^A-Z0-9]',
            '',
            'g'
        ) AS normalized_result_body,

        regexp_replace(
            UPPER(query_ticker),
            '[^A-Z0-9]',
            '',
            'g'
        ) AS normalized_query

    FROM bronze.eodhd_symbol_search_result
),

ranked AS (
    SELECT
        *,

        CASE
            WHEN parsed_ticker_body = query_ticker_upper
            THEN 1

            WHEN normalized_result_body = normalized_query
            THEN 2

            ELSE 99
        END AS match_rank,

        ROW_NUMBER() OVER (
            PARTITION BY query_ticker
            ORDER BY
                CASE
                    WHEN parsed_ticker_body = query_ticker_upper
                    THEN 1
                    WHEN normalized_result_body = normalized_query
                    THEN 2
                    ELSE 99
                END,
                result_rank
        ) AS rn

    FROM parsed
),

best AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)

SELECT
    query_ticker,

    result_code,
    parsed_ticker_body,

    result_exchange,
    result_name,
    result_type,
    result_country,
    result_currency,

    match_rank,

    CASE
        WHEN match_rank = 1
        THEN 'parsed_body_exact_match'

        WHEN match_rank = 2
        THEN 'punctuation_normalized_match'

        ELSE 'no_usable_search_match'
    END AS resolution_status

FROM best;
