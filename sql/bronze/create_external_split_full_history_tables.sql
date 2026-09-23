CREATE TABLE IF NOT EXISTS bronze.external_split_full_history_request (
    request_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    status_code INTEGER,
    response_json VARCHAR,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.external_split_full_history_observation (
    observation_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    split_date DATE NOT NULL,
    to_factor DOUBLE,
    for_factor DOUBLE,
    split_ratio DOUBLE,
    provider_split_text VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL
);
