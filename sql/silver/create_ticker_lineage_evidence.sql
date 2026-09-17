CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.ticker_lineage_evidence AS

WITH ticker_cik AS (
    SELECT
        md5(
            'quant_lodge|ticker_cik_mapping|' ||
            ticker || '|' || COALESCE(cik, '')
        ) AS evidence_id,

        'ticker_cik_mapping' AS claim_type,

        NULL::VARCHAR AS from_ticker,
        ticker AS to_ticker,
        cik,

        'quant_lodge' AS source_type,
        'Quant-Lodge/ticker-reference-data:data/ticker_changes.json'
            AS source_reference,

        flat_file_only,
        CURRENT_TIMESTAMP AS loaded_at

    FROM bronze.ticker_changes_external
    WHERE cik IS NOT NULL
),

predecessors AS (
    SELECT
        md5(
            'quant_lodge|historical_predecessor|' ||
            old_ticker || '|' ||
            ticker || '|' ||
            COALESCE(cik, '')
        ) AS evidence_id,

        'historical_predecessor' AS claim_type,

        old_ticker AS from_ticker,
        ticker AS to_ticker,
        cik,

        'quant_lodge' AS source_type,
        'Quant-Lodge/ticker-reference-data:data/ticker_changes.json'
            AS source_reference,

        flat_file_only,
        CURRENT_TIMESTAMP AS loaded_at

    FROM bronze.ticker_changes_external
    WHERE old_ticker IS NOT NULL
)

SELECT * FROM ticker_cik
UNION ALL
SELECT * FROM predecessors;
