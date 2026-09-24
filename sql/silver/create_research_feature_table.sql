-- ============================================================
-- Canonical technical research feature / label table
--
-- Feature horizons: 14, 20, 60 sessions
-- Prediction horizons: 1, 5, 10, 20, 60 sessions
--
-- Features use information available through close(t).
-- Forward targets start at t+1.
-- ============================================================


-- ------------------------------------------------------------
-- 1. Equal-weight primary-exchange common-equity market return
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_market_daily;

CREATE TABLE silver.research_market_daily AS

SELECT
    r.date,

    AVG(r.gross_total_return)
        AS market_return_1d,

    COUNT(*) AS market_security_count

FROM silver.security_daily_return_research r

JOIN silver.research_universe_eligibility u
  ON u.security_id = r.security_id
 AND u.date = r.date

WHERE r.final_research_eligible
  AND u.primary_research_eligible_exchange

GROUP BY r.date

ORDER BY r.date;
;


-- ------------------------------------------------------------
-- 2. Forward market returns
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_market_forward_return;

CREATE TABLE silver.research_market_forward_return AS

WITH x AS (
    SELECT
        date,
        market_return_1d,

        COUNT(market_return_1d) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING
        ) AS n_market_fwd_1,

        COUNT(market_return_1d) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 5 FOLLOWING
        ) AS n_market_fwd_5,

        COUNT(market_return_1d) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
        ) AS n_market_fwd_10,

        COUNT(market_return_1d) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
        ) AS n_market_fwd_20,

        COUNT(market_return_1d) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING
        ) AS n_market_fwd_60,


        SUM(LN(1.0 + market_return_1d)) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING
        ) AS market_fwd_log_1,

        SUM(LN(1.0 + market_return_1d)) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 5 FOLLOWING
        ) AS market_fwd_log_5,

        SUM(LN(1.0 + market_return_1d)) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
        ) AS market_fwd_log_10,

        SUM(LN(1.0 + market_return_1d)) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
        ) AS market_fwd_log_20,

        SUM(LN(1.0 + market_return_1d)) OVER (
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING
        ) AS market_fwd_log_60

    FROM silver.research_market_daily
)

SELECT
    *,

    CASE
        WHEN n_market_fwd_1 = 1
        THEN EXP(market_fwd_log_1) - 1.0
    END AS market_forward_return_1d,

    CASE
        WHEN n_market_fwd_5 = 5
        THEN EXP(market_fwd_log_5) - 1.0
    END AS market_forward_return_5d,

    CASE
        WHEN n_market_fwd_10 = 10
        THEN EXP(market_fwd_log_10) - 1.0
    END AS market_forward_return_10d,

    CASE
        WHEN n_market_fwd_20 = 20
        THEN EXP(market_fwd_log_20) - 1.0
    END AS market_forward_return_20d,

    CASE
        WHEN n_market_fwd_60 = 60
        THEN EXP(market_fwd_log_60) - 1.0
    END AS market_forward_return_60d

FROM x;
;


-- ------------------------------------------------------------
-- 3. Security forward returns
--
-- Partitioning by return_segment_id prevents labels crossing
-- quarantined / missing return observations.
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_forward_return_label;

CREATE TABLE silver.security_forward_return_label AS

WITH eligible AS (
    SELECT
        r.security_id,
        r.date,
        r.ticker,
        r.gross_total_return,

        g.return_segment_id

    FROM silver.security_daily_return_research r

    JOIN silver.security_gtr_index g
      ON g.security_id = r.security_id
     AND g.date = r.date

    WHERE r.final_research_eligible
),

x AS (
    SELECT
        *,

        COUNT(gross_total_return) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING
        ) AS n_fwd_1,

        COUNT(gross_total_return) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 5 FOLLOWING
        ) AS n_fwd_5,

        COUNT(gross_total_return) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
        ) AS n_fwd_10,

        COUNT(gross_total_return) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
        ) AS n_fwd_20,

        COUNT(gross_total_return) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING
        ) AS n_fwd_60,


        SUM(LN(1.0 + gross_total_return)) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING
        ) AS fwd_log_1,

        SUM(LN(1.0 + gross_total_return)) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 5 FOLLOWING
        ) AS fwd_log_5,

        SUM(LN(1.0 + gross_total_return)) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING
        ) AS fwd_log_10,

        SUM(LN(1.0 + gross_total_return)) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING
        ) AS fwd_log_20,

        SUM(LN(1.0 + gross_total_return)) OVER (
            PARTITION BY security_id, return_segment_id
            ORDER BY date
            ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING
        ) AS fwd_log_60

    FROM eligible
)

SELECT
    security_id,
    date,
    ticker,
    return_segment_id,

    CASE
        WHEN n_fwd_1 = 1
        THEN EXP(fwd_log_1) - 1.0
    END AS security_forward_return_1d,

    CASE
        WHEN n_fwd_5 = 5
        THEN EXP(fwd_log_5) - 1.0
    END AS security_forward_return_5d,

    CASE
        WHEN n_fwd_10 = 10
        THEN EXP(fwd_log_10) - 1.0
    END AS security_forward_return_10d,

    CASE
        WHEN n_fwd_20 = 20
        THEN EXP(fwd_log_20) - 1.0
    END AS security_forward_return_20d,

    CASE
        WHEN n_fwd_60 = 60
        THEN EXP(fwd_log_60) - 1.0
    END AS security_forward_return_60d

FROM x;
;


-- ------------------------------------------------------------
-- 4. Feature source
--
-- Compute rolling features BEFORE universe filtering so the
-- feature history follows the true eligible security series.
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_feature_source;

CREATE TABLE silver.research_feature_source AS

SELECT
    r.security_id,
    r.date,
    r.ticker,

    g.return_segment_id,

    r.gross_total_return,
    r.price_return,
    r.split_normalized_close,

    o.volume,

    LN(
        1.0 + GREATEST(
            CAST(o.volume AS DOUBLE),
            0.0
        )
    ) AS log_volume,

    m.market_return_1d,

    u.primary_research_eligible_broad,
    u.primary_research_eligible_exchange,

    r.split_normalized_close
      - LAG(r.split_normalized_close) OVER (
            PARTITION BY r.security_id, g.return_segment_id
            ORDER BY r.date
        ) AS price_delta

FROM silver.security_daily_return_research r

JOIN silver.security_gtr_index g
  ON g.security_id = r.security_id
 AND g.date = r.date

JOIN silver.security_daily_ohlcv_reconciled o
  ON o.security_id = r.security_id
 AND o.date = r.date

LEFT JOIN silver.research_market_daily m
  ON m.date = r.date

JOIN silver.research_universe_eligibility u
  ON u.security_id = r.security_id
 AND u.date = r.date

WHERE r.final_research_eligible;
;


-- ------------------------------------------------------------
-- 5. Rolling state variables
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_feature_rolling;

CREATE TABLE silver.research_feature_rolling AS

SELECT
    *,

    -- --------------------------------------------------------
    -- History counts
    -- --------------------------------------------------------

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS n_prior_14,

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS n_prior_20,

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
    ) AS n_prior_60,


    -- --------------------------------------------------------
    -- Trailing compounded returns INCLUDING date t
    -- --------------------------------------------------------

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS n_trailing_14,

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS n_trailing_20,

    COUNT(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
    ) AS n_trailing_60,


    SUM(LN(1.0 + gross_total_return)) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS trailing_log_return_14,

    SUM(LN(1.0 + gross_total_return)) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS trailing_log_return_20,

    SUM(LN(1.0 + gross_total_return)) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
    ) AS trailing_log_return_60,


    -- --------------------------------------------------------
    -- Realized volatility THROUGH t-1
    -- --------------------------------------------------------

    STDDEV_SAMP(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS realized_vol_14d_raw,

    STDDEV_SAMP(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS realized_vol_20d_raw,

    STDDEV_SAMP(gross_total_return) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
    ) AS realized_vol_60d_raw,


    -- --------------------------------------------------------
    -- Relative volume reference: trailing median through t-1
    -- --------------------------------------------------------

    MEDIAN(volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS median_volume_14,

    MEDIAN(volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS median_volume_20,

    MEDIAN(volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
    ) AS median_volume_60,


    -- --------------------------------------------------------
    -- Volume z-score reference through t-1
    -- --------------------------------------------------------

    AVG(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS mean_log_volume_14,

    AVG(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS mean_log_volume_20,

    AVG(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
    ) AS mean_log_volume_60,

    STDDEV_SAMP(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS sd_log_volume_14,

    STDDEV_SAMP(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS sd_log_volume_20,

    STDDEV_SAMP(log_volume) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING
    ) AS sd_log_volume_60,


    -- --------------------------------------------------------
    -- RSI components: current-inclusive price changes
    -- --------------------------------------------------------

    COUNT(price_delta) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS n_rsi_14,

    COUNT(price_delta) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS n_rsi_20,

    COUNT(price_delta) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
    ) AS n_rsi_60,


    SUM(
        CASE
            WHEN price_delta > 0
            THEN price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS gain_14,

    SUM(
        CASE
            WHEN price_delta < 0
            THEN -price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS loss_14,


    SUM(
        CASE
            WHEN price_delta > 0
            THEN price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS gain_20,

    SUM(
        CASE
            WHEN price_delta < 0
            THEN -price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS loss_20,


    SUM(
        CASE
            WHEN price_delta > 0
            THEN price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
    ) AS gain_60,

    SUM(
        CASE
            WHEN price_delta < 0
            THEN -price_delta
            ELSE 0.0
        END
    ) OVER (
        PARTITION BY security_id, return_segment_id
        ORDER BY date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
    ) AS loss_60

FROM silver.research_feature_source;
;


-- ------------------------------------------------------------
-- 6. Final feature / label table
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_feature_label;

CREATE TABLE silver.research_feature_label AS

WITH f AS (
    SELECT
        *,

        -- Current one-day return observed at close(t)
        gross_total_return AS lag_1d_gtr,


        -- Trailing compounded returns
        CASE
            WHEN n_trailing_14 = 14
            THEN EXP(trailing_log_return_14) - 1.0
        END AS trailing_gtr_14d,

        CASE
            WHEN n_trailing_20 = 20
            THEN EXP(trailing_log_return_20) - 1.0
        END AS trailing_gtr_20d,

        CASE
            WHEN n_trailing_60 = 60
            THEN EXP(trailing_log_return_60) - 1.0
        END AS trailing_gtr_60d,


        -- Realized vol
        CASE
            WHEN n_prior_14 = 14
            THEN realized_vol_14d_raw
        END AS realized_vol_14d,

        CASE
            WHEN n_prior_20 = 20
            THEN realized_vol_20d_raw
        END AS realized_vol_20d,

        CASE
            WHEN n_prior_60 = 60
            THEN realized_vol_60d_raw
        END AS realized_vol_60d,


        -- Relative volume
        CASE
            WHEN n_prior_14 = 14
             AND median_volume_14 > 0
            THEN volume / median_volume_14
        END AS relative_volume_14d,

        CASE
            WHEN n_prior_20 = 20
             AND median_volume_20 > 0
            THEN volume / median_volume_20
        END AS relative_volume_20d,

        CASE
            WHEN n_prior_60 = 60
             AND median_volume_60 > 0
            THEN volume / median_volume_60
        END AS relative_volume_60d,


        -- Volume z-score
        CASE
            WHEN n_prior_14 = 14
             AND sd_log_volume_14 > 0
            THEN
                (log_volume - mean_log_volume_14)
                / sd_log_volume_14
        END AS volume_zscore_14d,

        CASE
            WHEN n_prior_20 = 20
             AND sd_log_volume_20 > 0
            THEN
                (log_volume - mean_log_volume_20)
                / sd_log_volume_20
        END AS volume_zscore_20d,

        CASE
            WHEN n_prior_60 = 60
             AND sd_log_volume_60 > 0
            THEN
                (log_volume - mean_log_volume_60)
                / sd_log_volume_60
        END AS volume_zscore_60d,


        -- RSI (rolling / Cutler-style)
        CASE
            WHEN n_rsi_14 = 14
             AND gain_14 = 0
             AND loss_14 = 0
            THEN 50.0

            WHEN n_rsi_14 = 14
             AND loss_14 = 0
            THEN 100.0

            WHEN n_rsi_14 = 14
            THEN
                100.0
                - 100.0
                  / (
                      1.0
                      + gain_14 / NULLIF(loss_14, 0)
                    )
        END AS rsi_14,


        CASE
            WHEN n_rsi_20 = 20
             AND gain_20 = 0
             AND loss_20 = 0
            THEN 50.0

            WHEN n_rsi_20 = 20
             AND loss_20 = 0
            THEN 100.0

            WHEN n_rsi_20 = 20
            THEN
                100.0
                - 100.0
                  / (
                      1.0
                      + gain_20 / NULLIF(loss_20, 0)
                    )
        END AS rsi_20,


        CASE
            WHEN n_rsi_60 = 60
             AND gain_60 = 0
             AND loss_60 = 0
            THEN 50.0

            WHEN n_rsi_60 = 60
             AND loss_60 = 0
            THEN 100.0

            WHEN n_rsi_60 = 60
            THEN
                100.0
                - 100.0
                  / (
                      1.0
                      + gain_60 / NULLIF(loss_60, 0)
                    )
        END AS rsi_60

    FROM silver.research_feature_rolling
),

z AS (
    SELECT
        *,

        CASE
            WHEN realized_vol_14d > 0
            THEN lag_1d_gtr / realized_vol_14d
        END AS scaled_lag_1d_return_14d,

        CASE
            WHEN realized_vol_20d > 0
            THEN lag_1d_gtr / realized_vol_20d
        END AS scaled_lag_1d_return_20d,

        CASE
            WHEN realized_vol_60d > 0
            THEN lag_1d_gtr / realized_vol_60d
        END AS scaled_lag_1d_return_60d,

        CASE
            WHEN market_return_1d IS NOT NULL
             AND 1.0 + market_return_1d > 0
            THEN
                (1.0 + gross_total_return)
                / (1.0 + market_return_1d)
                - 1.0
        END AS market_relative_return_1d

    FROM f
),

joined AS (
    SELECT
        z.*,

        s.security_forward_return_1d,
        s.security_forward_return_5d,
        s.security_forward_return_10d,
        s.security_forward_return_20d,
        s.security_forward_return_60d,

        m.market_forward_return_1d,
        m.market_forward_return_5d,
        m.market_forward_return_10d,
        m.market_forward_return_20d,
        m.market_forward_return_60d

    FROM z

    LEFT JOIN silver.security_forward_return_label s
      ON s.security_id = z.security_id
     AND s.date = z.date

    LEFT JOIN silver.research_market_forward_return m
      ON m.date = z.date
)

SELECT
    security_id,
    date,
    ticker,
    return_segment_id,

    primary_research_eligible_broad,
    primary_research_eligible_exchange,

    CASE
        WHEN date <= DATE '2022-12-31'
        THEN 'train'

        WHEN date <= DATE '2024-12-31'
        THEN 'validation'

        ELSE 'test'
    END AS sample_split,


    -- ========================================================
    -- Features
    -- ========================================================

    lag_1d_gtr,

    trailing_gtr_14d,
    trailing_gtr_20d,
    trailing_gtr_60d,

    realized_vol_14d,
    realized_vol_20d,
    realized_vol_60d,

    scaled_lag_1d_return_14d,
    scaled_lag_1d_return_20d,
    scaled_lag_1d_return_60d,

    rsi_14,
    rsi_20,
    rsi_60,

    relative_volume_14d,
    relative_volume_20d,
    relative_volume_60d,

    volume_zscore_14d,
    volume_zscore_20d,
    volume_zscore_60d,

    market_return_1d,
    market_relative_return_1d,


    -- ========================================================
    -- Continuous forward security returns
    -- ========================================================

    security_forward_return_1d,
    security_forward_return_5d,
    security_forward_return_10d,
    security_forward_return_20d,
    security_forward_return_60d,


    -- ========================================================
    -- Continuous forward market-relative returns
    -- ========================================================

    CASE
        WHEN security_forward_return_1d IS NOT NULL
         AND market_forward_return_1d IS NOT NULL
        THEN
            (1.0 + security_forward_return_1d)
            / (1.0 + market_forward_return_1d)
            - 1.0
    END AS forward_rel_return_1d,

    CASE
        WHEN security_forward_return_5d IS NOT NULL
         AND market_forward_return_5d IS NOT NULL
        THEN
            (1.0 + security_forward_return_5d)
            / (1.0 + market_forward_return_5d)
            - 1.0
    END AS forward_rel_return_5d,

    CASE
        WHEN security_forward_return_10d IS NOT NULL
         AND market_forward_return_10d IS NOT NULL
        THEN
            (1.0 + security_forward_return_10d)
            / (1.0 + market_forward_return_10d)
            - 1.0
    END AS forward_rel_return_10d,

    CASE
        WHEN security_forward_return_20d IS NOT NULL
         AND market_forward_return_20d IS NOT NULL
        THEN
            (1.0 + security_forward_return_20d)
            / (1.0 + market_forward_return_20d)
            - 1.0
    END AS forward_rel_return_20d,

    CASE
        WHEN security_forward_return_60d IS NOT NULL
         AND market_forward_return_60d IS NOT NULL
        THEN
            (1.0 + security_forward_return_60d)
            / (1.0 + market_forward_return_60d)
            - 1.0
    END AS forward_rel_return_60d,


    -- ========================================================
    -- Classification targets
    -- ========================================================

    CASE
        WHEN security_forward_return_1d IS NULL
          OR market_forward_return_1d IS NULL
        THEN NULL
        WHEN
            (1.0 + security_forward_return_1d)
            / (1.0 + market_forward_return_1d)
            - 1.0 > 0
        THEN 1
        ELSE 0
    END AS target_outperform_1d,

    CASE
        WHEN security_forward_return_5d IS NULL
          OR market_forward_return_5d IS NULL
        THEN NULL
        WHEN
            (1.0 + security_forward_return_5d)
            / (1.0 + market_forward_return_5d)
            - 1.0 > 0
        THEN 1
        ELSE 0
    END AS target_outperform_5d,

    CASE
        WHEN security_forward_return_10d IS NULL
          OR market_forward_return_10d IS NULL
        THEN NULL
        WHEN
            (1.0 + security_forward_return_10d)
            / (1.0 + market_forward_return_10d)
            - 1.0 > 0
        THEN 1
        ELSE 0
    END AS target_outperform_10d,

    CASE
        WHEN security_forward_return_20d IS NULL
          OR market_forward_return_20d IS NULL
        THEN NULL
        WHEN
            (1.0 + security_forward_return_20d)
            / (1.0 + market_forward_return_20d)
            - 1.0 > 0
        THEN 1
        ELSE 0
    END AS target_outperform_20d,

    CASE
        WHEN security_forward_return_60d IS NULL
          OR market_forward_return_60d IS NULL
        THEN NULL
        WHEN
            (1.0 + security_forward_return_60d)
            / (1.0 + market_forward_return_60d)
            - 1.0 > 0
        THEN 1
        ELSE 0
    END AS target_outperform_60d

FROM joined

WHERE primary_research_eligible_broad;
