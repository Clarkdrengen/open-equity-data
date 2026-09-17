CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.ticker_transition AS

WITH candidates AS (
    SELECT
        e.evidence_id,
        e.from_ticker,
        e.to_ticker,
        e.cik,
        e.effective_date,
        e.relationship_type,
        e.same_issuer,
        e.same_security,
        e.source_type,
        e.source_reference,
        e.validation_method,
        e.evidence_strength,

        old_ep.ticker_episode_id AS from_episode_id,
        old_ep.start_date AS from_episode_start,
        old_ep.end_date AS from_episode_end,

        new_ep.ticker_episode_id AS to_episode_id,
        new_ep.start_date AS to_episode_start,
        new_ep.end_date AS to_episode_end,

        DATE_DIFF(
            'day',
            old_ep.end_date,
            e.effective_date
        ) AS days_old_end_to_effective,

        DATE_DIFF(
            'day',
            e.effective_date,
            new_ep.start_date
        ) AS days_effective_to_new_start,

        ROW_NUMBER() OVER (
            PARTITION BY e.evidence_id
            ORDER BY
                ABS(DATE_DIFF(
                    'day',
                    old_ep.end_date,
                    e.effective_date
                ))
                +
                ABS(DATE_DIFF(
                    'day',
                    e.effective_date,
                    new_ep.start_date
                ))
        ) AS candidate_rank

    FROM silver.ticker_transition_evidence e

    JOIN silver.ticker_episode old_ep
      ON old_ep.act_symbol = e.from_ticker
     AND old_ep.end_date <= e.effective_date

    JOIN silver.ticker_episode new_ep
      ON new_ep.act_symbol = e.to_ticker
     AND new_ep.start_date >= e.effective_date

    WHERE e.same_security = TRUE
),

best AS (
    SELECT *
    FROM candidates
    WHERE candidate_rank = 1
)

SELECT
    md5(
        evidence_id || '|' ||
        from_episode_id || '|' ||
        to_episode_id
    ) AS transition_id,

    evidence_id,

    from_episode_id,
    to_episode_id,

    from_ticker,
    to_ticker,
    cik,
    effective_date,
    relationship_type,

    same_issuer,
    same_security,

    from_episode_start,
    from_episode_end,
    to_episode_start,
    to_episode_end,

    days_old_end_to_effective,
    days_effective_to_new_start,

    CASE
        WHEN days_old_end_to_effective <= 4
         AND days_effective_to_new_start = 0
            THEN 'observed_transition'

        WHEN days_old_end_to_effective <= 4
         AND days_effective_to_new_start > 0
            THEN 'new_side_gap'

        WHEN days_old_end_to_effective > 4
         AND days_effective_to_new_start = 0
            THEN 'old_side_gap'

        ELSE 'both_sides_gap'
    END AS coverage_diagnostic,

    source_type,
    source_reference,
    validation_method,
    evidence_strength,

    CURRENT_TIMESTAMP AS materialized_at

FROM best;
