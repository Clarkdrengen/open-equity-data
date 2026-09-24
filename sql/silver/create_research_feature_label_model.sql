DROP TABLE IF EXISTS silver.research_feature_label_model;

CREATE TABLE silver.research_feature_label_model AS

WITH x AS (
    SELECT
        f.*,

        LEAD(date, 1) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
        ) AS target_end_date_1d,

        LEAD(date, 5) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
        ) AS target_end_date_5d,

        LEAD(date, 10) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
        ) AS target_end_date_10d,

        LEAD(date, 20) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
        ) AS target_end_date_20d,

        LEAD(date, 60) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
        ) AS target_end_date_60d

    FROM silver.research_feature_label f
)

SELECT
    *,

    CASE
        WHEN date <= DATE '2022-12-31'
         AND target_end_date_1d <= DATE '2022-12-31'
        THEN 'train'
        WHEN date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
         AND target_end_date_1d <= DATE '2024-12-31'
        THEN 'validation'
        WHEN date >= DATE '2025-01-01'
        THEN 'test'
    END AS split_1d,

    CASE
        WHEN date <= DATE '2022-12-31'
         AND target_end_date_5d <= DATE '2022-12-31'
        THEN 'train'
        WHEN date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
         AND target_end_date_5d <= DATE '2024-12-31'
        THEN 'validation'
        WHEN date >= DATE '2025-01-01'
        THEN 'test'
    END AS split_5d,

    CASE
        WHEN date <= DATE '2022-12-31'
         AND target_end_date_10d <= DATE '2022-12-31'
        THEN 'train'
        WHEN date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
         AND target_end_date_10d <= DATE '2024-12-31'
        THEN 'validation'
        WHEN date >= DATE '2025-01-01'
        THEN 'test'
    END AS split_10d,

    CASE
        WHEN date <= DATE '2022-12-31'
         AND target_end_date_20d <= DATE '2022-12-31'
        THEN 'train'
        WHEN date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
         AND target_end_date_20d <= DATE '2024-12-31'
        THEN 'validation'
        WHEN date >= DATE '2025-01-01'
        THEN 'test'
    END AS split_20d,

    CASE
        WHEN date <= DATE '2022-12-31'
         AND target_end_date_60d <= DATE '2022-12-31'
        THEN 'train'
        WHEN date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
         AND target_end_date_60d <= DATE '2024-12-31'
        THEN 'validation'
        WHEN date >= DATE '2025-01-01'
        THEN 'test'
    END AS split_60d

FROM x;
