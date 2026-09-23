CREATE OR REPLACE TEMP TABLE tmp_singleton_security_map AS
SELECT
    nextval('silver.security_id_seq') AS security_id,
    e.ticker_episode_id,
    e.start_date,
    e.end_date
FROM silver.ticker_episode e
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.ticker_lineage_membership lm
    WHERE lm.ticker_episode_id = e.ticker_episode_id
);

INSERT INTO silver.security_master (
    security_id,
    identity_status,
    lineage_id,
    first_observed_date,
    last_observed_date
)
SELECT
    nextval('silver.security_id_seq'),
    'validated_lineage',
    l.lineage_id,
    l.first_observed_date,
    l.last_observed_date
FROM silver.ticker_lineage_master l
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.security_master s
    WHERE s.lineage_id = l.lineage_id
);

INSERT INTO silver.security_episode_membership (
    security_id,
    ticker_episode_id,
    membership_method
)
SELECT
    s.security_id,
    lm.ticker_episode_id,
    'validated_lineage'
FROM silver.security_master s
JOIN silver.ticker_lineage_membership lm
  ON s.lineage_id = lm.lineage_id
WHERE s.identity_status = 'validated_lineage';

INSERT INTO silver.security_master (
    security_id,
    identity_status,
    lineage_id,
    first_observed_date,
    last_observed_date
)
SELECT
    security_id,
    'singleton_episode',
    NULL,
    start_date,
    end_date
FROM tmp_singleton_security_map;

INSERT INTO silver.security_episode_membership (
    security_id,
    ticker_episode_id,
    membership_method
)
SELECT
    security_id,
    ticker_episode_id,
    'singleton_episode'
FROM tmp_singleton_security_map;
