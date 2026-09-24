CREATE TABLE IF NOT EXISTS silver.corporate_action_override (
    security_id BIGINT NOT NULL,
    ticker VARCHAR NOT NULL,
    event_date DATE NOT NULL,

    corporate_action_type VARCHAR NOT NULL,
    dividend_share_basis VARCHAR NOT NULL,

    original_split_ratio DOUBLE,
    original_dividend_amount DOUBLE,

    override_split_ratio DOUBLE,
    override_dividend_amount DOUBLE,

    override_dividend_ex_date DATE,
    override_split_effective_date DATE,

    resolution_source VARCHAR NOT NULL,
    source_reference VARCHAR,
    resolution_notes VARCHAR NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (security_id, event_date)
);
