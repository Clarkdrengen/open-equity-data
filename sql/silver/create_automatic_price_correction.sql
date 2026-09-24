DROP TABLE IF EXISTS silver.automatic_price_correction;

CREATE TABLE silver.automatic_price_correction AS

WITH sessions AS (
    SELECT
        session_date,
        LAG(session_date) OVER (
            ORDER BY session_date
        ) AS previous_session
    FROM silver.trading_calendar
),

dividend_by_date AS (
    SELECT
        security_id,
        effective_dividend_ex_date AS date,

        SUM(
            CASE
                WHEN research_eligible
                THEN COALESCE(dividend_previous_share_basis, 0.0)
                ELSE 0.0
            END
        ) AS dividend_previous_share_basis,

        BOOL_OR(
            NOT research_eligible
            AND raw_dividend_amount > 0
        ) AS has_unresolved_positive_distribution

    FROM silver.security_dividend_event
    WHERE effective_dividend_ex_date IS NOT NULL
    GROUP BY 1,2
),

baseline AS (
    SELECT
        cur.security_id,
        cur.ticker,
        cur.date,
        s.previous_session AS previous_date,

        prev.close AS dolt_previous_close,
        cur.close AS dolt_current_close,

        fprev.cumulative_split_multiplier
            AS previous_split_multiplier,

        fcur.cumulative_split_multiplier
            AS current_split_multiplier,

        COALESCE(
            d.dividend_previous_share_basis,
            0.0
        ) AS dividend_previous_share_basis,

        COALESCE(
            d.has_unresolved_positive_distribution,
            FALSE
        ) AS has_unresolved_positive_distribution,

        cur.research_eligible
            AS current_price_research_eligible,

        prev.research_eligible
            AS previous_price_research_eligible

    FROM silver.security_daily_ohlcv cur

    JOIN sessions s
      ON s.session_date = cur.date

    JOIN silver.security_daily_ohlcv prev
      ON prev.security_id = cur.security_id
     AND prev.date = s.previous_session

    JOIN silver.security_daily_split_factor_reconciled fcur
      ON fcur.security_id = cur.security_id
     AND fcur.date = cur.date

    JOIN silver.security_daily_split_factor_reconciled fprev
      ON fprev.security_id = prev.security_id
     AND fprev.date = prev.date

    LEFT JOIN dividend_by_date d
      ON d.security_id = cur.security_id
     AND d.date = cur.date
),

returns AS (
    SELECT
        *,

        (
            dolt_current_close * current_split_multiplier
        )
        /
        (
            dolt_previous_close * previous_split_multiplier
        )
        - 1.0 AS dolt_price_return,

        (
            dolt_current_close * current_split_multiplier
            +
            dividend_previous_share_basis
                * previous_split_multiplier
        )
        /
        (
            dolt_previous_close * previous_split_multiplier
        )
        - 1.0 AS dolt_gross_total_return

    FROM baseline

    WHERE current_price_research_eligible
      AND previous_price_research_eligible
      AND NOT has_unresolved_positive_distribution
      AND dolt_previous_close > 0
),

provider AS (
    SELECT
        r.*,

        pp.close AS provider_previous_close,
        pc.close AS provider_current_close,

        pc.close / NULLIF(pp.close, 0) - 1.0
            AS provider_raw_return,

        pp.close / NULLIF(r.dolt_previous_close, 0)
            AS provider_to_dolt_previous_close_ratio,

        pc.close / NULLIF(r.dolt_current_close, 0)
            AS provider_to_dolt_current_close_ratio

    FROM returns r

    JOIN bronze.external_price_validation_observation pp
      ON pp.provider = 'EODHD'
     AND pp.ticker = r.ticker
     AND pp.date = r.previous_date

    JOIN bronze.external_price_validation_observation pc
      ON pc.provider = 'EODHD'
     AND pc.ticker = r.ticker
     AND pc.date = r.date
),

candidates AS (
    SELECT
        *,

        ABS(
            provider_to_dolt_previous_close_ratio - 1.0
        ) AS previous_ratio_error,

        ABS(
            provider_to_dolt_current_close_ratio - 1.0
        ) AS current_ratio_error

    FROM provider

    WHERE ABS(dolt_gross_total_return) > 1.0
      AND ABS(dolt_price_return) > 1.0
      AND ABS(provider_raw_return) <= 1.0
),

correction_dates AS (
    SELECT DISTINCT
        security_id,
        ticker,

        CASE
            WHEN current_ratio_error <= 0.01
             AND previous_ratio_error > 0.10
            THEN previous_date

            WHEN previous_ratio_error <= 0.01
             AND current_ratio_error > 0.10
            THEN date
        END AS correction_date,

        CASE
            WHEN current_ratio_error <= 0.01
             AND previous_ratio_error > 0.10
            THEN 'bad_previous_good_current'

            WHEN previous_ratio_error <= 0.01
             AND current_ratio_error > 0.10
            THEN 'good_previous_bad_current'
        END AS correction_reason

    FROM candidates

    WHERE (
            current_ratio_error <= 0.01
        AND previous_ratio_error > 0.10
    )
       OR (
            previous_ratio_error <= 0.01
        AND current_ratio_error > 0.10
    )
)

SELECT
    c.security_id,
    c.ticker,
    c.correction_date,

    e.open,
    e.high,
    e.low,
    e.close,
    e.volume,
    e.adjusted_close,

    e.provider,
    e.provider_symbol,

    c.correction_reason,

    'high_confidence_one_sided_vendor_match'
        AS resolution_method

FROM correction_dates c

JOIN bronze.external_price_validation_observation e
  ON e.provider = 'EODHD'
 AND e.ticker = c.ticker
 AND e.date = c.correction_date;
