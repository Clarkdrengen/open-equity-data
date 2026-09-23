CREATE TABLE IF NOT EXISTS bronze.eodhd_symbol_reference (
    provider_symbol VARCHAR NOT NULL,
    code VARCHAR NOT NULL,
    exchange VARCHAR,
    name VARCHAR,
    country VARCHAR,
    currency VARCHAR,
    instrument_type VARCHAR,
    isin VARCHAR,
    is_delisted BOOLEAN NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_payload_json VARCHAR NOT NULL,
    PRIMARY KEY (provider_symbol, is_delisted)
);
