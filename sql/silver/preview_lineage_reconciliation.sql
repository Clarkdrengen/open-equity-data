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

component_existing_lineages AS (
    SELECT
        c.component_root,
        COUNT(DISTINCT m.lineage_id) AS existing_lineage_count,
        MIN(m.lineage_id) AS existing_lineage_id
    FROM components c
    LEFT JOIN silver.ticker_lineage_membership m
      ON m.ticker_episode_id = c.episode_id
    GROUP BY c.component_root
),

component_stats AS (
    SELECT
        c.component_root,
        COUNT(*) AS episode_count,
        MIN(e.start_date) AS first_observed_date,
        MAX(e.end_date) AS last_observed_date,
        arg_max(e.act_symbol, e.end_date) AS latest_ticker
    FROM components c
    JOIN silver.ticker_episode e
      ON e.ticker_episode_id = c.episode_id
    GROUP BY c.component_root
)

SELECT
    s.component_root,
    s.episode_count,
    s.latest_ticker,
    s.first_observed_date,
    s.last_observed_date,
    x.existing_lineage_count,
    x.existing_lineage_id,

    CASE
        WHEN x.existing_lineage_count = 0
            THEN 'CREATE_NEW_LINEAGE'
        WHEN x.existing_lineage_count = 1
            THEN 'REUSE_EXISTING_LINEAGE'
        ELSE 'MANUAL_MERGE_REQUIRED'
    END AS reconciliation_action

FROM component_stats s
JOIN component_existing_lineages x
  ON x.component_root = s.component_root

ORDER BY reconciliation_action, s.latest_ticker;
