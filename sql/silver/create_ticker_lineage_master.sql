CREATE SEQUENCE IF NOT EXISTS silver.lineage_id_seq START 1;

CREATE TABLE IF NOT EXISTS silver.ticker_lineage_master (
    lineage_id BIGINT PRIMARY KEY,
    lineage_code VARCHAR,
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
