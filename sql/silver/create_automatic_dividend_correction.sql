DROP TABLE IF EXISTS silver.automatic_dividend_correction;

CREATE TABLE silver.automatic_dividend_correction AS

SELECT
    security_id,
    ticker,
    effective_dividend_ex_date AS event_date,

    dividend_previous_share_basis AS original_dividend_amount,
    eodhd_unadjusted AS corrected_dividend_amount,
    eodhd_adjusted,

    dividend_previous_share_basis
        / NULLIF(eodhd_unadjusted, 0)
        AS retrospective_adjustment_factor,

    'EODHD' AS provider,
    'retrospective_adjustment_correction'
        AS resolution_method

FROM silver.dividend_validation_25pct

WHERE validation_status =
      'retrospective_adjustment_correction';
