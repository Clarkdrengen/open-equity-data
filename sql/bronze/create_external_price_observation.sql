CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.external_price_request (
    request_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    lineage_id BIGINT NOT NULL,
    lineage_code VARCHAR,
    historical_ticker VARCHAR,
    session_date DATE NOT NULL,
    lookup_method VARCHAR NOT NULL,
    result_count INTEGER NOT NULL,
    response_json VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.external_price_observation (
    observation_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    lineage_id BIGINT NOT NULL,
    lineage_code VARCHAR,
    historical_ticker VARCHAR,
    session_date DATE NOT NULL,
    lookup_method VARCHAR NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    provider_adjusted_close DOUBLE,
    provider_volume BIGINT,
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL
);
