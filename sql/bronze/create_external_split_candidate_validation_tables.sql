CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.external_split_candidate_validation_request (
    request_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    status_code INTEGER,
    response_row_count INTEGER,
    error_text VARCHAR,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.external_split_candidate_validation_observation (
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    ex_date DATE NOT NULL,
    split_factor_text VARCHAR,
    split_ratio DOUBLE,
    request_id VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL,
    PRIMARY KEY (provider, provider_symbol, ex_date, split_factor_text)
);
