CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.external_price_validation_request (
    request_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    status_code INTEGER,
    response_row_count INTEGER,
    error_text VARCHAR,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.external_price_validation_observation (
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    date DATE NOT NULL,

    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adjusted_close DOUBLE,
    volume BIGINT,

    request_id VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL,

    PRIMARY KEY (provider, provider_symbol, date)
);
