CREATE TABLE IF NOT EXISTS silver.eodhd_symbol_resolution (
    ticker VARCHAR NOT NULL,
    relevant_date DATE NOT NULL,

    resolution_status VARCHAR NOT NULL,
    resolved_provider_symbol VARCHAR,

    resolution_method VARCHAR NOT NULL,
    notes VARCHAR,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ticker, relevant_date)
);
