CREATE OR REPLACE TABLE silver.ticker_lineage_preview AS

WITH RECURSIVE

edges AS (
    SELECT from_episode_id AS a, to_episode_id AS b
    FROM silver.ticker_transition
    WHERE same_security = TRUE

    UNION ALL

    SELECT to_episode_id AS a, from_episode_id AS b
    FROM silver.ticker_transition
    WHERE same_security = TRUE
),

nodes AS (
    SELECT a AS episode_id FROM edges
    UNION
    SELECT b AS episode_id FROM edges
),

reach(root_episode_id, episode_id) AS (
    SELECT episode_id, episode_id
    FROM nodes

    UNION

    SELECT
        r.root_episode_id,
        e.b
    FROM reach r
    JOIN edges e
      ON e.a = r.episode_id
),

components AS (
    SELECT
        episode_id,
        MIN(root_episode_id) AS component_root
    FROM reach
    GROUP BY episode_id
),

membership AS (
    SELECT
        c.component_root,
        e.ticker_episode_id,
        e.act_symbol,
        e.start_date,
        e.end_date,
        e.n_observations
    FROM components c
    JOIN silver.ticker_episode e
      ON e.ticker_episode_id = c.episode_id
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY component_root
            ORDER BY end_date DESC, start_date DESC
        ) AS latest_rank
    FROM membership
),

latest AS (
    SELECT
        component_root,
        act_symbol AS latest_ticker
    FROM ranked
    WHERE latest_rank = 1
)

SELECT
    l.latest_ticker || '_1' AS lineage_code,
    m.ticker_episode_id,
    m.act_symbol,
    m.start_date,
    m.end_date,
    m.n_observations
FROM membership m
JOIN latest l
  ON l.component_root = m.component_root
ORDER BY lineage_code, start_date;
