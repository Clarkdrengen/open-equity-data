DROP TABLE IF EXISTS silver.security_split_candidate;

CREATE TABLE silver.security_split_candidate AS

WITH split_source AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                act_symbol,
                source_ex_date,
                to_factor,
                for_factor,
                previous_trading_date,
                event_close
        ) AS source_split_row_id,
        *
    FROM silver.split_audit
),

episode_candidates AS (
    SELECT
        a.source_split_row_id,
        e.ticker_episode_id,
        e.start_date,
        e.end_date,

        CASE
            WHEN a.source_ex_date BETWEEN e.start_date AND e.end_date
            THEN 0
            ELSE LEAST(
                ABS(date_diff('day', a.source_ex_date, e.start_date)),
                ABS(date_diff('day', a.source_ex_date, e.end_date))
            )
        END AS episode_distance_days,

        ROW_NUMBER() OVER (
            PARTITION BY a.source_split_row_id
            ORDER BY
                CASE
                    WHEN a.source_ex_date BETWEEN e.start_date AND e.end_date
                    THEN 0
                    ELSE LEAST(
                        ABS(date_diff('day', a.source_ex_date, e.start_date)),
                        ABS(date_diff('day', a.source_ex_date, e.end_date))
                    )
                END,
                e.start_date,
                e.ticker_episode_id
        ) AS rn

    FROM split_source a
    JOIN silver.ticker_episode e
      ON e.act_symbol = a.act_symbol
),

best_episode AS (
    SELECT
        source_split_row_id,
        ticker_episode_id,
        start_date,
        end_date,
        episode_distance_days
    FROM episode_candidates
    WHERE rn = 1
),

mapped AS (
    SELECT
        a.*,

        b.ticker_episode_id AS candidate_ticker_episode_id,
        b.episode_distance_days,

        CASE
            WHEN b.ticker_episode_id IS NULL
            THEN 'unresolved_no_episode'

            WHEN a.source_ex_date BETWEEN b.start_date AND b.end_date
            THEN 'exact_episode_date'

            WHEN b.episode_distance_days <= 7
            THEN 'nearest_episode_within_7d'

            WHEN b.episode_distance_days <= 30
            THEN 'nearest_episode_8_30d'

            ELSE 'unresolved_distance_gt_30d'
        END AS episode_mapping_method

    FROM split_source a
    LEFT JOIN best_episode b
      ON a.source_split_row_id = b.source_split_row_id
)

SELECT
    m.source_split_row_id,

    CASE
        WHEN m.episode_mapping_method IN (
            'exact_episode_date',
            'nearest_episode_within_7d'
        )
        THEN sem.security_id
        ELSE NULL
    END AS security_id,

    m.candidate_ticker_episode_id,
    m.episode_mapping_method,
    m.episode_distance_days,

    m.act_symbol AS ticker,
    m.source_ex_date,

    m.to_factor,
    m.for_factor,
    m.stated_ratio,

    m.previous_trading_date,
    m.previous_close,
    m.event_close,
    m.raw_price_ratio,
    m.implied_return,

    m.has_price_on_ex_date,

    m.nearby_same_ratio_count,
    (m.nearby_same_ratio_count > 0)
        AS nearby_same_ratio_duplicate,

    (
        m.implied_return IS NOT NULL
        AND ABS(m.implied_return) > 0.50
    ) AS large_implied_return,

    m.suspicious_flag,

    CASE
        WHEN NOT m.suspicious_flag
             AND m.episode_mapping_method = 'exact_episode_date'
        THEN 'provisionally_accepted'

        ELSE 'requires_reconciliation'
    END AS validation_status,

    CASE
        WHEN NOT m.suspicious_flag
             AND m.episode_mapping_method = 'exact_episode_date'
        THEN m.source_ex_date
        ELSE NULL
    END AS validated_ex_date,

    CASE
        WHEN NOT m.suspicious_flag
             AND m.episode_mapping_method = 'exact_episode_date'
        THEN m.stated_ratio
        ELSE NULL
    END AS validated_ratio,

    CASE
        WHEN NOT m.suspicious_flag
             AND m.episode_mapping_method = 'exact_episode_date'
        THEN 'dolt_split_audit'
        ELSE NULL
    END AS validation_source

FROM mapped m

LEFT JOIN silver.security_episode_membership sem
  ON sem.ticker_episode_id = m.candidate_ticker_episode_id;
