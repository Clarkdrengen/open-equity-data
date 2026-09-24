DROP TABLE IF EXISTS silver.security_dividend_event;

CREATE TABLE silver.security_dividend_event AS

WITH base AS (
    SELECT
        d.security_id,
        d.ticker,
        d.ex_date,
        d.amount AS raw_dividend_amount,
        d.previous_close,
        d.validation_status AS source_validation_status,
        f_cur.daily_split_ratio,
        f_cur.cumulative_split_multiplier AS current_multiplier,
        f_prev.cumulative_split_multiplier AS previous_multiplier,
        o.corporate_action_type,
        o.dividend_share_basis,
        o.override_split_ratio,
        o.override_dividend_amount,
        a.corrected_dividend_amount AS automatic_corrected_dividend_amount,
        o.override_dividend_ex_date,
        o.override_split_effective_date,
        o.resolution_source,
        o.source_reference,
        o.resolution_notes
    FROM silver.security_dividend_candidate d
    JOIN silver.security_daily_split_factor f_cur
      ON f_cur.security_id = d.security_id
     AND f_cur.date = d.ex_date
    JOIN (
        SELECT
            session_date,
            LAG(session_date) OVER (ORDER BY session_date) AS previous_session
        FROM silver.trading_calendar
    ) prev_cal
      ON prev_cal.session_date = d.ex_date
    JOIN silver.security_daily_split_factor f_prev
      ON f_prev.security_id = d.security_id
     AND f_prev.date = prev_cal.previous_session
    LEFT JOIN silver.corporate_action_override o
      ON o.security_id = d.security_id
     AND o.event_date = d.ex_date

    LEFT JOIN silver.automatic_dividend_correction a
      ON a.security_id = d.security_id
     AND a.event_date = d.ex_date
),
resolved AS (
    SELECT
        *,
        COALESCE(override_dividend_amount, raw_dividend_amount)
            AS effective_dividend_amount,
        COALESCE(override_dividend_ex_date, ex_date)
            AS effective_dividend_ex_date,
        CASE
            WHEN corporate_action_type =
                 'composite_cash_and_in_kind_distribution'
            THEN NULL
            WHEN corporate_action_type = 'stock_dividend'
            THEN 0.0
            WHEN dividend_share_basis = 'pre_split'
            THEN COALESCE(override_dividend_amount, raw_dividend_amount)
            WHEN dividend_share_basis = 'post_split'
            THEN COALESCE(override_dividend_amount, raw_dividend_amount)
                 * COALESCE(override_split_ratio, daily_split_ratio)
            WHEN daily_split_ratio = 1.0
            THEN COALESCE(
                automatic_corrected_dividend_amount,
                raw_dividend_amount
            )
            ELSE NULL
        END AS dividend_previous_share_basis,
        CASE
            WHEN corporate_action_type =
                 'composite_cash_and_in_kind_distribution'
            THEN 'unresolved_composite_distribution'
            WHEN corporate_action_type = 'stock_dividend'
            THEN 'manual_stock_dividend_only'
            WHEN dividend_share_basis = 'pre_split'
            THEN 'manual_pre_split_basis'
            WHEN dividend_share_basis = 'post_split'
            THEN 'manual_post_split_basis'
            WHEN daily_split_ratio = 1.0
            THEN 'standard_cash_dividend'
            ELSE 'unresolved_same_day_split_basis'
        END AS dividend_resolution_method
    FROM base
)
SELECT
    security_id,
    ticker,
    ex_date,
    effective_dividend_ex_date,
    raw_dividend_amount,
    effective_dividend_amount,
    dividend_previous_share_basis,
    daily_split_ratio,
    corporate_action_type,
    dividend_share_basis,
    dividend_resolution_method,
    source_validation_status,
    resolution_source,
    source_reference,
    resolution_notes,
    CASE
        WHEN dividend_previous_share_basis IS NOT NULL
         AND (
             raw_dividend_amount > 0
             OR corporate_action_type = 'stock_dividend'
         )
        THEN TRUE
        ELSE FALSE
    END AS research_eligible
FROM resolved;
