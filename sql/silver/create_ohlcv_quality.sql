CREATE OR REPLACE TABLE silver.ohlcv_quality AS

WITH observations AS (
    SELECT
        o.*,
        c.session_date IS NOT NULL AS is_expected_session
    FROM bronze.ohlcv o
    LEFT JOIN silver.trading_calendar c
      ON c.session_date = o.date
),

closed_rows AS (
    SELECT
        o.*,

        (
            SELECT MAX(c.session_date)
            FROM silver.trading_calendar c
            WHERE c.session_date < o.date
        ) AS previous_session,

        (
            SELECT MIN(c.session_date)
            FROM silver.trading_calendar c
            WHERE c.session_date > o.date
        ) AS next_session

    FROM observations o
    WHERE NOT is_expected_session
),

closed_classified AS (
    SELECT
        b.date,
        b.act_symbol,

        CASE
            WHEN p.date IS NOT NULL
             AND b.open   = p.open
             AND b.high   = p.high
             AND b.low    = p.low
             AND b.close  = p.close
             AND b.volume = p.volume
            THEN TRUE ELSE FALSE
        END AS duplicate_previous,

        CASE
            WHEN n.date IS NOT NULL
             AND b.open   = n.open
             AND b.high   = n.high
             AND b.low    = n.low
             AND b.close  = n.close
             AND b.volume = n.volume
            THEN TRUE ELSE FALSE
        END AS duplicate_next

    FROM closed_rows b

    LEFT JOIN bronze.ohlcv p
      ON p.act_symbol = b.act_symbol
     AND p.date = b.previous_session

    LEFT JOIN bronze.ohlcv n
      ON n.act_symbol = b.act_symbol
     AND n.date = b.next_session
)

SELECT
    o.date,
    o.act_symbol,

    CASE
        WHEN o.is_expected_session
            THEN 'valid_session'

        WHEN c.duplicate_previous
         AND c.duplicate_next
            THEN 'closed_session_duplicate_both'

        WHEN c.duplicate_previous
            THEN 'closed_session_duplicate_previous'

        WHEN c.duplicate_next
            THEN 'closed_session_duplicate_next'

        ELSE 'closed_session_anomalous'
    END AS quality_status,

    o.is_expected_session

FROM observations o

LEFT JOIN closed_classified c
  ON c.date = o.date
 AND c.act_symbol = o.act_symbol;
