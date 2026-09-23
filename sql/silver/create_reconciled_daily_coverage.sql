DROP TABLE IF EXISTS silver.reconciled_daily_coverage;

CREATE TABLE silver.reconciled_daily_coverage AS

WITH expected AS (
    SELECT
        m.lineage_id,
        m.lineage_code,
        c.session_date
    FROM silver.ticker_lineage_master m
    JOIN silver.trading_calendar c
      ON c.session_date BETWEEN m.first_observed_date AND m.last_observed_date
),

observed AS (
    SELECT
        lineage_id,
        date AS session_date,
        TRUE AS has_observation,
        BOOL_OR(research_eligible) AS has_research_eligible_observation
    FROM silver.reconciled_ohlcv
    GROUP BY 1, 2
)

SELECT
    e.lineage_id,
    e.lineage_code,
    e.session_date,

    COALESCE(o.has_observation, FALSE) AS has_observation,
    COALESCE(o.has_research_eligible_observation, FALSE)
        AS has_research_eligible_observation

FROM expected e
LEFT JOIN observed o
  ON e.lineage_id = o.lineage_id
 AND e.session_date = o.session_date;
