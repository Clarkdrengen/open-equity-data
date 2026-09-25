-- ============================================================
-- Point-in-time shares outstanding
--
-- Primary source:
--   EODHD quarterly Balance Sheet
--
-- Availability convention:
--   an observation becomes usable on filing_date,
--   NOT on the fiscal period date.
--
-- This layer does not yet apply SEC class-specific overrides.
-- Those will be overlaid for multi-listed-class issuers.
-- ============================================================


-- ------------------------------------------------------------
-- 1. Clean / deduplicate raw EODHD observations
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_shares_outstanding_observation;

CREATE TABLE silver.security_shares_outstanding_observation AS

WITH raw AS (
    SELECT
        ticker,
        provider_symbol,
        period_date,
        filing_date,
        common_stock_shares_outstanding
            AS shares_outstanding,
        currency_symbol,
        retrieved_at,

        ROW_NUMBER() OVER (
            PARTITION BY
                ticker,
                period_date,
                filing_date
            ORDER BY retrieved_at DESC
        ) AS rn

    FROM bronze.eodhd_fundamental_balance_sheet_observation

    WHERE filing_date IS NOT NULL
      AND period_date IS NOT NULL
      AND common_stock_shares_outstanding IS NOT NULL
      AND common_stock_shares_outstanding > 0
)

SELECT
    ticker,
    provider_symbol,
    period_date,
    filing_date,
    shares_outstanding,
    currency_symbol,
    retrieved_at,
    'eodhd_balance_sheet' AS shares_source

FROM raw

WHERE rn = 1
  AND period_date <= filing_date;
;


-- ------------------------------------------------------------
-- 2. One effective shares observation per ticker / filing date
--
-- A filing can contain multiple historical balance-sheet periods.
-- For PIT use, take the latest fiscal period available on that
-- filing date.
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_shares_outstanding_effective;

CREATE TABLE silver.security_shares_outstanding_effective AS

SELECT
    ticker,
    provider_symbol,
    period_date,
    filing_date,
    shares_outstanding,
    currency_symbol,
    retrieved_at,
    shares_source

FROM silver.security_shares_outstanding_observation

QUALIFY ROW_NUMBER() OVER (
    PARTITION BY
        ticker,
        filing_date
    ORDER BY
        period_date DESC,
        retrieved_at DESC
) = 1;
;


-- ------------------------------------------------------------
-- 3. Ticker identity diagnostics
--
-- Multiple security_ids can reflect episode fragmentation and are
-- not automatically problematic.
--
-- Multiple distinct ISINs for the same ticker are a stronger sign
-- of ticker reuse / identity ambiguity.
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.shares_ticker_identity_diagnostic;

CREATE TABLE silver.shares_ticker_identity_diagnostic AS

SELECT
    ticker,

    COUNT(DISTINCT security_id)
        AS distinct_security_ids,

    COUNT(DISTINCT resolved_isin)
        FILTER (
            WHERE resolved_isin IS NOT NULL
        )
        AS distinct_isins,

    MIN(resolved_isin)
        FILTER (
            WHERE resolved_isin IS NOT NULL
        )
        AS single_candidate_isin,

    CASE
        WHEN COUNT(DISTINCT resolved_isin)
             FILTER (
                 WHERE resolved_isin IS NOT NULL
             ) > 1
        THEN TRUE
        ELSE FALSE
    END AS ticker_identity_ambiguous

FROM silver.security_ticker_reference_resolution

WHERE resolved_instrument_type = 'Common Stock'

GROUP BY ticker;
;


-- ------------------------------------------------------------
-- 4. Daily PIT shares
--
-- ASOF JOIN selects the most recently FILED observation available
-- on each research date.
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_daily_shares_outstanding_pit;

CREATE TABLE silver.security_daily_shares_outstanding_pit AS

WITH research_dates AS (
    SELECT
        security_id,
        date,
        ticker
    FROM silver.research_universe_eligibility
    WHERE primary_research_eligible_exchange
),

pit AS (
    SELECT
        d.security_id,
        d.date,
        d.ticker,

        o.provider_symbol,
        o.period_date
            AS shares_period_date,
        o.filing_date
            AS shares_filing_date,
        o.shares_outstanding,
        o.shares_source,

        date_diff(
            'day',
            o.filing_date,
            d.date
        ) AS shares_age_days

    FROM research_dates d

    ASOF LEFT JOIN
        silver.security_shares_outstanding_effective o

      ON d.ticker = o.ticker
     AND d.date >= o.filing_date
)

SELECT
    p.*,

    COALESCE(
        i.distinct_security_ids,
        0
    ) AS ticker_security_id_count,

    COALESCE(
        i.distinct_isins,
        0
    ) AS ticker_isin_count,

    COALESCE(
        i.ticker_identity_ambiguous,
        FALSE
    ) AS ticker_identity_ambiguous,

    CASE
        WHEN p.shares_outstanding IS NULL
        THEN 'missing'

        WHEN p.shares_age_days <= 120
        THEN 'fresh'

        WHEN p.shares_age_days <= 180
        THEN 'acceptable'

        WHEN p.shares_age_days <= 365
        THEN 'stale'

        ELSE 'very_stale'
    END AS shares_freshness,

    CASE
        WHEN p.shares_outstanding IS NOT NULL
         AND p.shares_age_days <= 365
         AND NOT COALESCE(
                i.ticker_identity_ambiguous,
                FALSE
             )
        THEN TRUE
        ELSE FALSE
    END AS shares_pit_available

FROM pit p

LEFT JOIN silver.shares_ticker_identity_diagnostic i
  ON i.ticker = p.ticker;
