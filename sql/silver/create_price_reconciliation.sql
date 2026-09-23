DROP TABLE IF EXISTS silver.price_reconciliation;

CREATE TABLE silver.price_reconciliation AS

SELECT
    o.lineage_id,
    o.lineage_code,
    o.session_date AS date,

    o.historical_ticker AS ticker,

    o.open,
    o.high,
    o.low,
    o.close,
    o.provider_volume AS volume,

    'eodhd' AS source,
    o.provider_symbol AS source_symbol,
    o.lookup_method AS source_lookup_method,

    CASE
        WHEN o.provider_volume = 0
             AND o.open = o.high
             AND o.high = o.low
             AND o.low = o.close
        THEN 'external_zero_volume_observation'

        WHEN o.lookup_method = 'lineage_latest_ticker_fallback'
        THEN 'accepted_external_fill_lineage_fallback'

        ELSE 'accepted_external_fill'
    END AS reconciliation_status,

    CASE
        WHEN o.provider_volume = 0
             AND o.open = o.high
             AND o.high = o.low
             AND o.low = o.close
        THEN 'external_zero_volume_bar'

        ELSE 'external_traded_bar'
    END AS observation_type,

    CASE
        WHEN o.provider_volume = 0
             AND o.open = o.high
             AND o.high = o.low
             AND o.low = o.close
        THEN FALSE

        ELSE TRUE
    END AS research_eligible,

    o.provider_adjusted_close,
    o.retrieved_at

FROM bronze.external_price_observation o;
