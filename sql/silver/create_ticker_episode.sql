CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.ticker_episode AS
WITH ordered AS (
    SELECT
        act_symbol,
        date,
        LAG(date) OVER (
            PARTITION BY act_symbol
            ORDER BY date
        ) AS previous_date
    FROM bronze.ohlcv
),

breaks AS (
    SELECT
        act_symbol,
        date,
        previous_date,
        CASE
            WHEN previous_date IS NULL THEN 1
            WHEN DATE_DIFF('day', previous_date, date) > 7 THEN 1
            ELSE 0
        END AS new_episode
    FROM ordered
),

numbered AS (
    SELECT
        act_symbol,
        date,
        previous_date,
        SUM(new_episode) OVER (
            PARTITION BY act_symbol
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS episode_number
    FROM breaks
),

episode_stats AS (
    SELECT
        act_symbol,
        episode_number,
        MIN(date) AS start_date,
        MAX(date) AS end_date,
        COUNT(*) AS n_observations,
        MAX(
            CASE
                WHEN previous_date IS NOT NULL
                THEN DATE_DIFF('day', previous_date, date)
            END
        ) AS max_internal_gap_days
    FROM numbered
    GROUP BY
        act_symbol,
        episode_number
)

SELECT
    act_symbol || '_E' ||
        LPAD(CAST(episode_number AS VARCHAR), 3, '0')
        AS ticker_episode_id,
    act_symbol,
    episode_number,
    start_date,
    end_date,
    n_observations,
    max_internal_gap_days
FROM episode_stats
ORDER BY act_symbol, episode_number;
