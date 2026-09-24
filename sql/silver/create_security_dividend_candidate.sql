DROP TABLE IF EXISTS silver.security_dividend_candidate;

CREATE TABLE silver.security_dividend_candidate AS

WITH sessions AS (
    SELECT
        session_date,
        LAG(session_date) OVER (
            ORDER BY session_date
        ) AS previous_session
    FROM silver.trading_calendar
)

SELECT
    sem.security_id,
    e.ticker_episode_id,

    d.act_symbol AS ticker,
    d.ex_date,
    CAST(d.amount AS DOUBLE) AS amount,

    s.previous_session,

    prev.close AS previous_close,

    CAST(d.amount AS DOUBLE)
        / NULLIF(prev.close, 0)
        AS raw_indicated_dividend_yield,

    CASE
        WHEN d.amount = 0
        THEN 'zero_source_artifact'

        WHEN CAST(d.amount AS DOUBLE)
             / NULLIF(prev.close, 0) > 0.25
        THEN 'requires_reconciliation'

        ELSE 'provisionally_accepted'
    END AS validation_status

FROM bronze.dividend d

JOIN silver.ticker_episode e
  ON e.act_symbol = d.act_symbol
 AND d.ex_date BETWEEN e.start_date AND e.end_date

JOIN silver.security_episode_membership sem
  ON sem.ticker_episode_id = e.ticker_episode_id

JOIN sessions s
  ON s.session_date = d.ex_date

JOIN silver.security_daily_ohlcv cur
  ON cur.security_id = sem.security_id
 AND cur.date = d.ex_date
 AND cur.research_eligible

JOIN silver.security_daily_ohlcv prev
  ON prev.security_id = sem.security_id
 AND prev.date = s.previous_session
 AND prev.research_eligible;
