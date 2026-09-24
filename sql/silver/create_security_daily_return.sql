DROP TABLE IF EXISTS silver.security_daily_return;

CREATE TABLE silver.security_daily_return AS

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
        ) AS has_unresolved_positive_distribution,

        COUNT(*) AS dividend_source_rows,

        COUNT(*) FILTER (
            WHERE research_eligible
        ) AS eligible_dividend_rows

    FROM silver.security_dividend_event

    WHERE effective_dividend_ex_date IS NOT NULL

    GROUP BY 1, 2
),

joined AS (
    SELECT
        cur.security_id,
        cur.date,
        cur.ticker,

        cur.source,
        cur.source_symbol,
        cur.source_lookup_method,

        cur.close,
        cur.daily_split_ratio,
        cur.cumulative_split_multiplier,
        cur.split_normalized_close,

        s.previous_session AS previous_date,

        prev.close AS previous_close,
        prev.cumulative_split_multiplier
            AS previous_cumulative_split_multiplier,
        prev.split_normalized_close
            AS previous_split_normalized_close,

        cur.price_research_eligible
            AS current_price_research_eligible,

        prev.price_research_eligible
            AS previous_price_research_eligible,

        COALESCE(
            d.dividend_previous_share_basis,
            0.0
        ) AS dividend_previous_share_basis,

        COALESCE(
            d.dividend_previous_share_basis,
            0.0
        ) * prev.cumulative_split_multiplier
            AS split_normalized_dividend,

        COALESCE(
            d.has_unresolved_positive_distribution,
            FALSE
        ) AS has_unresolved_positive_distribution,

        COALESCE(d.dividend_source_rows, 0)
            AS dividend_source_rows,

        COALESCE(d.eligible_dividend_rows, 0)
            AS eligible_dividend_rows

    FROM silver.security_daily_return_basis cur

    JOIN sessions s
      ON s.session_date = cur.date

    LEFT JOIN silver.security_daily_return_basis prev
      ON prev.security_id = cur.security_id
     AND prev.date = s.previous_session

    LEFT JOIN dividend_by_date d
      ON d.security_id = cur.security_id
     AND d.date = cur.date
),

classified AS (
    SELECT
        *,

        CASE
            WHEN NOT current_price_research_eligible
            THEN 'current_price_not_research_eligible'

            WHEN previous_date IS NULL
            THEN 'no_previous_market_session'

            WHEN previous_split_normalized_close IS NULL
            THEN 'missing_previous_price'

            WHEN NOT COALESCE(
                previous_price_research_eligible,
                FALSE
            )
            THEN 'previous_price_not_research_eligible'

            WHEN has_unresolved_positive_distribution
            THEN 'unresolved_positive_distribution'

            WHEN previous_split_normalized_close <= 0
            THEN 'invalid_previous_price'

            ELSE 'eligible'
        END AS return_status

    FROM joined
)

SELECT
    security_id,
    date,
    ticker,

    source,
    source_symbol,
    source_lookup_method,

    close,
    daily_split_ratio,
    cumulative_split_multiplier,
    split_normalized_close,

    previous_date,
    previous_close,
    previous_cumulative_split_multiplier,
    previous_split_normalized_close,

    dividend_previous_share_basis,
    split_normalized_dividend,
    dividend_source_rows,
    eligible_dividend_rows,

    CASE
        WHEN return_status = 'eligible'
        THEN split_normalized_close
             / previous_split_normalized_close
             - 1.0
        ELSE NULL
    END AS price_return,

    CASE
        WHEN return_status = 'eligible'
        THEN (
            split_normalized_close
            + split_normalized_dividend
        ) / previous_split_normalized_close
        - 1.0
        ELSE NULL
    END AS gross_total_return,

    return_status,

    (return_status = 'eligible')
        AS research_eligible

FROM classified;
