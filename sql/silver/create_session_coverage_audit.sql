CREATE OR REPLACE TABLE silver.session_coverage_audit AS

WITH calendar AS (
    SELECT
        session_date,
        session_minutes,
        is_early_close,

        LAG(session_date) OVER (
            ORDER BY session_date
        ) AS previous_session,

        LEAD(session_date) OVER (
            ORDER BY session_date
        ) AS next_session

    FROM silver.trading_calendar
),

continuing AS (
    SELECT
        c.session_date,
        c.session_minutes,
        c.is_early_close,
        c.previous_session,
        c.next_session,
        p.act_symbol

    FROM calendar c

    JOIN silver.clean_ohlcv p
      ON p.date = c.previous_session

    JOIN silver.clean_ohlcv n
      ON n.date = c.next_session
     AND n.act_symbol = p.act_symbol

    WHERE c.previous_session IS NOT NULL
      AND c.next_session IS NOT NULL
),

coverage AS (
    SELECT
        c.session_date,
        c.session_minutes,
        c.is_early_close,

        MIN(c.previous_session) AS previous_session,
        MIN(c.next_session) AS next_session,

        COUNT(*) AS expected_continuing_tickers,

        SUM(
            CASE
                WHEN d.act_symbol IS NOT NULL THEN 1
                ELSE 0
            END
        ) AS observed_continuing_tickers

    FROM continuing c

    LEFT JOIN silver.clean_ohlcv d
      ON d.date = c.session_date
     AND d.act_symbol = c.act_symbol

    GROUP BY
        c.session_date,
        c.session_minutes,
        c.is_early_close
),

metrics AS (
    SELECT
        *,

        expected_continuing_tickers
        - observed_continuing_tickers
            AS missing_continuing_tickers,

        100.0 * observed_continuing_tickers
        / NULLIF(expected_continuing_tickers, 0)
            AS continuity_coverage_pct

    FROM coverage
)

SELECT
    *,

    CASE
        WHEN continuity_coverage_pct < 80
            THEN 'extreme_low_coverage'

        WHEN continuity_coverage_pct < 97
            THEN 'low_coverage'

        WHEN continuity_coverage_pct < 99
            THEN 'moderate_low_coverage'

        ELSE 'normal_coverage'
    END AS coverage_status

FROM metrics
ORDER BY session_date;
