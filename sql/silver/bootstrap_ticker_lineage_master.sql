CREATE SEQUENCE IF NOT EXISTS silver.lineage_id_seq START 1;

CREATE TABLE IF NOT EXISTS silver.ticker_lineage_master (
    lineage_id BIGINT PRIMARY KEY,
    lineage_code VARCHAR UNIQUE,
    latest_ticker VARCHAR,
    first_observed_date DATE,
    last_observed_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.ticker_lineage_membership (
    lineage_id BIGINT,
    ticker_episode_id VARCHAR,
    sequence_number INTEGER,
    PRIMARY KEY (lineage_id, ticker_episode_id)
);

-- Bootstrap new validated lineages.
INSERT INTO silver.ticker_lineage_master
SELECT
    nextval('silver.lineage_id_seq') AS lineage_id,
    lineage_code,
    arg_max(act_symbol, end_date) AS latest_ticker,
    MIN(start_date) AS first_observed_date,
    MAX(end_date) AS last_observed_date,
    CURRENT_TIMESTAMP AS created_at,
    CURRENT_TIMESTAMP AS updated_at
FROM silver.ticker_lineage_preview p
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.ticker_lineage_master m
    WHERE m.lineage_code = p.lineage_code
)
GROUP BY lineage_code;

-- Populate episode membership.
INSERT INTO silver.ticker_lineage_membership
SELECT
    m.lineage_id,
    p.ticker_episode_id,
    ROW_NUMBER() OVER (
        PARTITION BY m.lineage_id
        ORDER BY p.start_date, p.ticker_episode_id
    ) AS sequence_number
FROM silver.ticker_lineage_preview p
JOIN silver.ticker_lineage_master m
  ON m.lineage_code = p.lineage_code
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.ticker_lineage_membership x
    WHERE x.lineage_id = m.lineage_id
      AND x.ticker_episode_id = p.ticker_episode_id
);
