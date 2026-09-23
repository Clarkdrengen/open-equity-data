CREATE SEQUENCE IF NOT EXISTS silver.security_id_seq START 1;

CREATE TABLE IF NOT EXISTS silver.security_master (
    security_id BIGINT PRIMARY KEY,
    identity_status VARCHAR NOT NULL,
    lineage_id BIGINT,
    first_observed_date DATE,
    last_observed_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.security_episode_membership (
    security_id BIGINT NOT NULL,
    ticker_episode_id VARCHAR NOT NULL,
    membership_method VARCHAR NOT NULL,
    PRIMARY KEY (security_id, ticker_episode_id)
);
