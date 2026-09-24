DROP TABLE IF EXISTS silver.automatic_split_backfill;

CREATE TABLE silver.automatic_split_backfill AS
SELECT
    security_id,
    ticker,
    date AS split_date,
    provider_split_ratio AS split_ratio,
    provider_raw_return,
    provider_adjusted_return,
    counterfactual_return_with_provider_split,
    adjusted_return_abs_error,
    'EODHD' AS provider,
    'extreme_return_exact_date_mechanical_validation' AS resolution_method
FROM silver.split_backfill_validation
WHERE exact_date_missing_split_validated;

CREATE UNIQUE INDEX IF NOT EXISTS
    automatic_split_backfill_security_date_idx
ON silver.automatic_split_backfill (security_id, split_date);
