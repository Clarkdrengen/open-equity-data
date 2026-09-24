CREATE TABLE IF NOT EXISTS bronze.external_dividend_request (
    request_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,
    status_code INTEGER,
    response_json VARCHAR,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.external_dividend_observation (
    observation_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    provider_symbol VARCHAR NOT NULL,

    ex_date DATE,
    declaration_date DATE,
    record_date DATE,
    payment_date DATE,

    value DOUBLE,
    unadjusted_value DOUBLE,
    currency VARCHAR,

    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL
);
