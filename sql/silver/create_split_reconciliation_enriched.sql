DROP TABLE IF EXISTS silver.split_reconciliation_enriched;

CREATE TABLE silver.split_reconciliation_enriched AS

SELECT
    c.*,

    r.resolution_status AS provider_identity_status,
    r.resolved_provider_symbol,
    r.resolution_method AS provider_identity_method,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN c.security_id

        WHEN r.resolution_status = 'resolved'
        THEN sem.security_id

        ELSE NULL
    END AS resolved_security_id,

    CASE
        WHEN c.security_id IS NOT NULL
        THEN 'existing_security_mapping'

        WHEN r.resolution_status = 'resolved'
         AND sem.security_id IS NOT NULL
        THEN 'provider_identity_resolution'

        WHEN r.resolution_status = 'unresolved'
        THEN 'provider_identity_ambiguous'

        ELSE 'unresolved'
    END AS security_resolution_method

FROM silver.split_external_comparison c

LEFT JOIN silver.eodhd_symbol_resolution r
  ON r.ticker = c.ticker
 AND r.relevant_date = c.provider_split_date

LEFT JOIN silver.ticker_episode e
  ON e.act_symbol = c.ticker
 AND c.provider_split_date BETWEEN e.start_date AND e.end_date

LEFT JOIN silver.security_episode_membership sem
  ON sem.ticker_episode_id = e.ticker_episode_id;
