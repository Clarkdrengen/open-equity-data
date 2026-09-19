CREATE OR REPLACE TABLE silver.daily_coverage AS

WITH expected AS (
    SELECT
        m.lineage_id,
        m.lineage_code,
        c.session_date
    FROM silver.ticker_lineage_master m
    JOIN silver.trading_calendar c
      ON c.session_date BETWEEN
         m.first_observed_date AND m.last_observed_date
)

SELECT
    e.lineage_id,
    e.lineage_code,
    e.session_date,

    o.date IS NOT NULL AS observation_present,
    o.ticker_episode_id,
    o.act_symbol,
    o.close,
    o.volume,

    CASE
        WHEN o.date IS NOT NULL THEN 'observed'
        ELSE 'missing_expected_session'
    END AS coverage_status

FROM expected e

LEFT JOIN silver.lineage_ohlcv o
  ON o.lineage_id = e.lineage_id
 AND o.date = e.session_date

ORDER BY
    e.lineage_id,
    e.session_date;
