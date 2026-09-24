DROP TABLE IF EXISTS silver.same_day_split_dividend_candidate;

CREATE TABLE silver.same_day_split_dividend_candidate AS

WITH sessions AS (
    SELECT
        session_date,
        LAG(session_date) OVER (
            ORDER BY session_date
        ) AS previous_session
    FROM silver.trading_calendar
)

SELECT
    d.security_id,
    d.ticker,
    d.ex_date,

    d.amount AS raw_dividend_amount,

    s.split_ratio,
    s.to_factor,
    s.for_factor,
    s.validation_source AS split_validation_source,
    s.validation_method AS split_validation_method,

    prev.close AS previous_close,
    cur.close AS event_close,

    f_prev.cumulative_split_multiplier
        AS previous_split_multiplier,

    f_cur.cumulative_split_multiplier
        AS event_split_multiplier,

    -- What the dividend would be on the previous-share basis
    -- IF the source dividend is quoted per post-split share.
    d.amount * s.split_ratio
        AS dividend_prev_basis_if_post_split_quote,

    -- Dividend yield if source amount is already pre-split basis.
    d.amount / NULLIF(prev.close, 0)
        AS yield_if_pre_split_quote,

    -- Dividend yield if source amount is post-split basis.
    (d.amount * s.split_ratio)
        / NULLIF(prev.close, 0)
        AS yield_if_post_split_quote,

    'unresolved'::VARCHAR AS dividend_share_basis,
    'unresolved'::VARCHAR AS event_order,
    NULL::VARCHAR AS resolution_source,
    NULL::VARCHAR AS resolution_notes

FROM silver.security_dividend_candidate d

JOIN silver.security_split_event s
  ON s.security_id = d.security_id
 AND s.split_date = d.ex_date

JOIN sessions cal
  ON cal.session_date = d.ex_date

JOIN silver.security_daily_ohlcv prev
  ON prev.security_id = d.security_id
 AND prev.date = cal.previous_session
 AND prev.research_eligible

JOIN silver.security_daily_ohlcv cur
  ON cur.security_id = d.security_id
 AND cur.date = d.ex_date
 AND cur.research_eligible

JOIN silver.security_daily_split_factor f_prev
  ON f_prev.security_id = d.security_id
 AND f_prev.date = cal.previous_session

JOIN silver.security_daily_split_factor f_cur
  ON f_cur.security_id = d.security_id
 AND f_cur.date = d.ex_date;
