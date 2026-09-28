-- Source-backed manual shares. When the optional EODHD target is supplied,
-- that exact vendor observation is invalidated in Silver; original Bronze
-- source rows are never rewritten. Without a target this can fill a gap.
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.eodhd_share_manual_adjustment (
    security_id BIGINT NOT NULL,
    ticker VARCHAR NOT NULL,
    target_provider_symbol VARCHAR,
    target_period_date DATE,
    target_filing_date DATE,
    target_shares DOUBLE,
    sourced_shares DOUBLE NOT NULL,
    shares_as_of_date DATE NOT NULL,
    source_publication_date DATE NOT NULL,
    source_name VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL,
    source_document_id VARCHAR NOT NULL,
    source_excerpt VARCHAR NOT NULL,
    source_document_sha256 VARCHAR,
    recorded_at TIMESTAMP NOT NULL,
    CHECK (target_shares IS NULL OR target_shares > 0),
    CHECK (sourced_shares > 0),
    CHECK (shares_as_of_date <= source_publication_date),
    CHECK (
        (target_provider_symbol IS NULL AND target_period_date IS NULL
         AND target_filing_date IS NULL AND target_shares IS NULL)
        OR
        (target_provider_symbol IS NOT NULL AND target_period_date IS NOT NULL
         AND target_filing_date IS NOT NULL AND target_shares IS NOT NULL)
    )
);
