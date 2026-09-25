-- ============================================================
-- Security-aware instrument reference resolution
--
-- Resolution hierarchy:
--   1. manual override
--   2. explicit ticker syntax
--   3. exact EODHD reference
--   4. bronze.symbol metadata
--   5. canonicalized EODHD reference (_old, dash/dot)
--   6. unresolved
--
-- Delisted status is descriptive only. It is NEVER an
-- eligibility filter.
-- ============================================================


-- ------------------------------------------------------------
-- 0. Small explicit override table
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.security_reference_manual_override (
    ticker VARCHAR PRIMARY KEY,
    instrument_type VARCHAR NOT NULL,
    resolution_source VARCHAR NOT NULL,
    resolution_notes VARCHAR
);

INSERT OR REPLACE INTO silver.security_reference_manual_override
VALUES
    (
        'TI.A',
        'Common Stock',
        'manual_reference_override',
        'Historical Telecom Italia class-share listing; ordinary/common equity.'
    ),
    (
        'XAN',
        'Common Stock',
        'manual_reference_override',
        'Exantas Capital Corp. listed common equity; descriptive provider metadata insufficient.'
    ),
    (
        'KST',
        'FUND',
        'manual_reference_override',
        'Deutsche Strategic Income Trust; closed-end investment fund, not ordinary common equity.'
    );


-- ------------------------------------------------------------
-- 1. Observed security/ticker spans
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_reference_candidate;

CREATE TABLE silver.security_reference_candidate AS

WITH ticker_span AS (
    SELECT
        security_id,
        ticker,
        MIN(date) AS first_date,
        MAX(date) AS last_date
    FROM silver.security_daily_return_research
    GROUP BY 1,2
),

eodhd AS (
    SELECT
        *,
        replace(
            regexp_replace(
                UPPER(code),
                '_OLD[0-9]*$',
                ''
            ),
            '-',
            '.'
        ) AS canonical_code
    FROM bronze.eodhd_symbol_reference
)

SELECT
    t.security_id,
    t.ticker,
    t.first_date,
    t.last_date,

    r.provider_symbol,
    r.code AS provider_code,
    r.instrument_type,
    r.exchange,
    r.name,
    r.isin,
    r.is_delisted,

    CASE
        WHEN UPPER(r.code) = UPPER(t.ticker)
        THEN 'exact_code'
        ELSE 'canonicalized_code'
    END AS candidate_method

FROM ticker_span t

JOIN eodhd r
  ON UPPER(r.code) = UPPER(t.ticker)
  OR r.canonical_code = UPPER(t.ticker);
;


-- ------------------------------------------------------------
-- 2. Latest bronze.symbol metadata
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_symbol_fallback;

CREATE TABLE silver.security_symbol_fallback AS

WITH latest_symbol AS (
    SELECT *
    FROM bronze.symbol
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY UPPER(act_symbol)
        ORDER BY last_seen DESC NULLS LAST
    ) = 1
)

SELECT
    act_symbol AS ticker,
    security_name,
    listing_exchange,
    market_category,
    is_etf,
    is_test_issue,
    financial_status,
    last_seen,

    CASE
        -- Explicit symbol semantics first
        WHEN act_symbol LIKE '%$%'
        THEN 'Preferred Stock'

        WHEN regexp_matches(
            UPPER(act_symbol),
            '\.W(S)?$'
        )
        THEN 'Warrant'

        WHEN regexp_matches(
            UPPER(act_symbol),
            '\.U$'
        )
        THEN 'Unit'

        WHEN regexp_matches(
            UPPER(act_symbol),
            '\.R$'
        )
        THEN 'Right'


        -- Test instruments
        WHEN is_test_issue = 1
          OR UPPER(security_name) LIKE '%TEST SYMBOL%'
          OR UPPER(security_name) LIKE '%TEST COMPANY%'
        THEN 'Test Issue'


        -- Structured ETF flag
        WHEN is_etf = 1
        THEN 'ETF'


        -- Temporary / when-issued instruments
        WHEN UPPER(security_name) LIKE '%WHEN-ISSUED%'
          OR UPPER(security_name) LIKE '%WHEN ISSUED%'
          OR UPPER(security_name) LIKE '%EX-DISTRIBUTION%'
        THEN 'When-Issued'
        -- Preferred securities.
        --
        -- Require explicit security-type wording. Do not classify merely
        -- because an issuer name contains words such as "Preferred"
        -- (for example Preferred Bank common stock).

        WHEN (
                UPPER(security_name) LIKE '%PREFERRED STOCK%'
             OR UPPER(security_name) LIKE '%PREFERRED SHARE%'
             OR UPPER(security_name) LIKE '% PFD%'
             OR UPPER(security_name) LIKE '%PFD %'
             OR (
                    UPPER(security_name) LIKE '%DEPOSITARY SHARE%'
                AND UPPER(security_name) LIKE '%PREFERRED%'
             )
        )
        AND UPPER(security_name) NOT LIKE '%COMMON STOCK%'
        THEN 'Preferred Stock'


        -- Warrants / units / rights.
        --
        -- Require explicit instrument wording. Broad substring rules such
        -- as %RIGHT% misclassify Curtiss-Wright and ADR descriptions that
        -- merely contain the phrase "right to receive".

        WHEN regexp_matches(
            UPPER(security_name),
            '(^| - | )WARRANT(S)?([ ,(]|$)'
        )
        THEN 'Warrant'

        -- Preferred units are economically preferred securities rather
        -- than ordinary/common equity.
        WHEN regexp_matches(
            UPPER(security_name),
            'PREFERRED UNIT(S)?([ ,(]|$)'
        )
        THEN 'Preferred Stock'

        WHEN regexp_matches(
            UPPER(security_name),
            '(^| - | )UNIT(S)?([ ,(]|$)'
        )
          OR UPPER(security_name) LIKE '%COMMON UNITS%'
          OR UPPER(security_name) LIKE '%LIMITED PARTNER INTERESTS%'
          OR UPPER(security_name) LIKE '%LIMITED PARTNERSHIP UNITS%'
        THEN 'Unit'

        WHEN regexp_matches(
            UPPER(security_name),
            '(^| - | )RIGHT(S)?([ ,(]|$)'
        )
        THEN 'Right'


        -- ETNs / index-linked notes

        WHEN UPPER(security_name) LIKE '% ETN%'
          OR UPPER(security_name) LIKE '%ETRACS%'
          OR UPPER(security_name) LIKE '%EXCHANGE TRADED NOTE%'
          OR UPPER(security_name) LIKE '%EXCHANGE-TRADED NOTE%'
          OR UPPER(security_name) LIKE '%INDEX SERIES%'
          OR UPPER(security_name) LIKE '%LINKED TO THE % INDEX%'
          OR UPPER(security_name) LIKE '%LINKED TO THE MORNINGSTAR%'
        THEN 'ETN'


        -- Debt securities
        WHEN UPPER(security_name) LIKE '%NOTES DUE%'
          OR UPPER(security_name) LIKE '%SENIOR NOTE%'
          OR UPPER(security_name) LIKE '%SENIOR SECURED NOTE%'
          OR UPPER(security_name) LIKE '%SENIOR UNSECURED NOTE%'
          OR UPPER(security_name) LIKE '%SUBORDINATED NOTE%'
          OR UPPER(security_name) LIKE '%DEBENTURE%'
          OR UPPER(security_name) LIKE '%STRUCTURED REPACKAGED%'
          OR UPPER(security_name) LIKE '%FIXED-INCOME%'
        THEN 'Notes'

        -- Explicit fund vehicles.
        --
        -- Do not treat every "Shares of Beneficial Interest" security as
        -- a fund: that wording is also used by REITs and other listed
        -- equity vehicles.

        WHEN UPPER(security_name) LIKE '%CLOSED END FUND%'
          OR UPPER(security_name) LIKE '%CLOSED-END FUND%'
        THEN 'FUND'


        -- Ordinary/common equity

        WHEN UPPER(security_name) LIKE '%COMMON STOCK%'
          OR UPPER(security_name) LIKE '%COMMON SHARE%'
          OR UPPER(security_name) LIKE '%COMMON SHARES%'
          OR UPPER(security_name) LIKE '%ORDINARY SHARE%'
          OR UPPER(security_name) LIKE '%ORDINARY SHARES%'
          OR UPPER(security_name) LIKE '%CLASS A VOTING SHARES%'
          OR UPPER(security_name) LIKE '%CLASS B NON-VOTING SHARES%'
          OR UPPER(security_name) LIKE '%AMERICAN DEPOSITARY%'
        THEN 'Common Stock'

        ELSE NULL
    END AS inferred_instrument_type

FROM latest_symbol;
;


-- ------------------------------------------------------------
-- 3. Aggregate EODHD evidence by security/ticker
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_ticker_reference_resolution;

CREATE TABLE silver.security_ticker_reference_resolution AS

WITH ticker_span AS (
    SELECT
        security_id,
        ticker,
        MIN(date) AS first_date,
        MAX(date) AS last_date
    FROM silver.security_daily_return_research
    GROUP BY 1,2
),

exact_eodhd AS (
    SELECT
        security_id,
        ticker,

        COUNT(*) AS candidate_rows,

        COUNT(DISTINCT instrument_type)
            FILTER (WHERE instrument_type IS NOT NULL)
            AS n_types,

        COUNT(DISTINCT exchange)
            FILTER (WHERE exchange IS NOT NULL)
            AS n_exchanges,

        COUNT(DISTINCT isin)
            FILTER (WHERE isin IS NOT NULL)
            AS n_isins,

        MIN(instrument_type)
            FILTER (WHERE instrument_type IS NOT NULL)
            AS instrument_type,

        MIN(exchange)
            FILTER (WHERE exchange IS NOT NULL)
            AS exchange,

        MIN(isin)
            FILTER (WHERE isin IS NOT NULL)
            AS isin,

        BOOL_OR(NOT is_delisted)
            AS has_active_reference,

        BOOL_OR(is_delisted)
            AS has_delisted_reference

    FROM silver.security_reference_candidate

    WHERE candidate_method = 'exact_code'

    GROUP BY 1,2
),

canonical_eodhd AS (
    SELECT
        security_id,
        ticker,

        COUNT(*) AS candidate_rows,

        COUNT(DISTINCT instrument_type)
            FILTER (WHERE instrument_type IS NOT NULL)
            AS n_types,

        COUNT(DISTINCT exchange)
            FILTER (WHERE exchange IS NOT NULL)
            AS n_exchanges,

        COUNT(DISTINCT isin)
            FILTER (WHERE isin IS NOT NULL)
            AS n_isins,

        MIN(instrument_type)
            FILTER (WHERE instrument_type IS NOT NULL)
            AS instrument_type,

        MIN(exchange)
            FILTER (WHERE exchange IS NOT NULL)
            AS exchange,

        MIN(isin)
            FILTER (WHERE isin IS NOT NULL)
            AS isin,

        BOOL_OR(NOT is_delisted)
            AS has_active_reference,

        BOOL_OR(is_delisted)
            AS has_delisted_reference

    FROM silver.security_reference_candidate

    WHERE candidate_method = 'canonicalized_code'

    GROUP BY 1,2
),

joined AS (
    SELECT
        t.security_id,
        t.ticker,
        t.first_date,
        t.last_date,

        m.instrument_type
            AS manual_instrument_type,

        -- Explicit ticker semantics.
        CASE
            WHEN t.ticker LIKE '%$%'
            THEN 'Preferred Stock'

            WHEN regexp_matches(
                UPPER(t.ticker),
                '\.W(S)?$'
            )
            THEN 'Warrant'

            WHEN regexp_matches(
                UPPER(t.ticker),
                '\.U$'
            )
            THEN 'Unit'

            WHEN regexp_matches(
                UPPER(t.ticker),
                '\.R$'
            )
            THEN 'Right'

            ELSE NULL
        END AS syntax_instrument_type,

        e.candidate_rows
            AS exact_candidate_rows,

        e.n_types
            AS exact_n_types,

        e.n_exchanges
            AS exact_n_exchanges,

        e.instrument_type
            AS exact_instrument_type,

        e.exchange
            AS exact_exchange,

        e.isin
            AS exact_isin,

        e.has_active_reference
            AS exact_has_active,

        e.has_delisted_reference
            AS exact_has_delisted,

        b.inferred_instrument_type
            AS bronze_instrument_type,

        b.listing_exchange
            AS bronze_exchange,

        b.security_name
            AS bronze_security_name,

        b.last_seen
            AS bronze_last_seen,

        c.candidate_rows
            AS canonical_candidate_rows,

        c.n_types
            AS canonical_n_types,

        c.n_exchanges
            AS canonical_n_exchanges,

        c.instrument_type
            AS canonical_instrument_type,

        c.exchange
            AS canonical_exchange,

        c.isin
            AS canonical_isin,

        c.has_active_reference
            AS canonical_has_active,

        c.has_delisted_reference
            AS canonical_has_delisted

    FROM ticker_span t

    LEFT JOIN silver.security_reference_manual_override m
      ON UPPER(m.ticker) = UPPER(t.ticker)

    LEFT JOIN exact_eodhd e
      ON e.security_id = t.security_id
     AND e.ticker = t.ticker

    LEFT JOIN silver.security_symbol_fallback b
      ON UPPER(b.ticker) = UPPER(t.ticker)

    LEFT JOIN canonical_eodhd c
      ON c.security_id = t.security_id
     AND c.ticker = t.ticker
)

SELECT
    *,

    
    CASE
        WHEN manual_instrument_type IS NOT NULL
        THEN manual_instrument_type

        WHEN syntax_instrument_type IS NOT NULL
        THEN syntax_instrument_type

        -- High-confidence structured / explicit Bronze evidence vetoes an
        -- erroneous EODHD Common Stock label.
        WHEN bronze_instrument_type IN (
            'Warrant',
            'Right',
            'Unit',
            'ETF',
            'ETN',
            'Test Issue',
            'When-Issued',
            'Preferred Stock',
            'Notes',
            'FUND'
        )
        THEN bronze_instrument_type

        WHEN exact_n_types = 1
        THEN exact_instrument_type

        WHEN bronze_instrument_type IS NOT NULL
        THEN bronze_instrument_type

        WHEN canonical_n_types = 1
        THEN canonical_instrument_type

        ELSE NULL
    END AS resolved_instrument_type,



    CASE
        WHEN exact_n_exchanges = 1
        THEN exact_exchange

        WHEN bronze_exchange IS NOT NULL
        THEN bronze_exchange

        WHEN canonical_n_exchanges = 1
        THEN canonical_exchange

        ELSE NULL
    END AS resolved_exchange,


    COALESCE(
        exact_isin,
        canonical_isin
    ) AS resolved_isin,


    COALESCE(
        exact_has_active,
        canonical_has_active,
        FALSE
    ) AS has_active_reference,


    COALESCE(
        exact_has_delisted,
        canonical_has_delisted,
        FALSE
    ) AS has_delisted_reference,


    CASE
        WHEN manual_instrument_type IS NOT NULL
        THEN 'resolved_manual_override'

        
        WHEN syntax_instrument_type IS NOT NULL
        THEN 'resolved_symbol_syntax'

        WHEN bronze_instrument_type IN (
            'Warrant',
            'Right',
            'Unit',
            'ETF',
            'ETN',
            'Test Issue',
            'When-Issued',
            'Preferred Stock',
            'Notes',
            'FUND'
        )
        THEN 'resolved_bronze_explicit_noncommon'

        WHEN exact_n_types = 1
        THEN 'resolved_eodhd_exact'

        WHEN exact_n_types > 1
        THEN 'ambiguous_eodhd_exact'

        WHEN bronze_instrument_type IS NOT NULL
        THEN 'resolved_bronze_symbol'


        WHEN canonical_n_types = 1
        THEN 'resolved_eodhd_canonical'

        WHEN canonical_n_types > 1
        THEN 'ambiguous_eodhd_canonical'

        ELSE 'unresolved'
    END AS reference_resolution_status

FROM joined;
;


-- ------------------------------------------------------------
-- 4. Security-level summary
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.security_reference_resolution;

CREATE TABLE silver.security_reference_resolution AS

WITH x AS (
    SELECT
        security_id,

        COUNT(*) AS observed_tickers,

        COUNT(*) FILTER (
            WHERE resolved_instrument_type IS NOT NULL
        ) AS resolved_tickers,

        COUNT(*) FILTER (
            WHERE resolved_instrument_type IS NULL
        ) AS unresolved_tickers,

        COUNT(DISTINCT resolved_instrument_type)
            FILTER (
                WHERE resolved_instrument_type IS NOT NULL
            ) AS distinct_resolved_types,

        MIN(resolved_instrument_type)
            FILTER (
                WHERE resolved_instrument_type IS NOT NULL
            ) AS candidate_security_type

    FROM silver.security_ticker_reference_resolution

    GROUP BY security_id
)

SELECT
    *,

    CASE
        WHEN distinct_resolved_types = 1
        THEN candidate_security_type
        ELSE NULL
    END AS resolved_security_type,

    CASE
        WHEN resolved_tickers = observed_tickers
         AND distinct_resolved_types = 1
        THEN 'resolved_all_tickers_consistent'

        WHEN resolved_tickers > 0
         AND distinct_resolved_types = 1
        THEN 'partially_resolved_consistent'

        WHEN distinct_resolved_types > 1
        THEN 'ticker_history_type_conflict'

        ELSE 'unresolved'
    END AS security_reference_status

FROM x;
;


-- ------------------------------------------------------------
-- 5. Dated research-universe eligibility
-- ------------------------------------------------------------

DROP TABLE IF EXISTS silver.research_universe_eligibility;

CREATE TABLE silver.research_universe_eligibility AS

SELECT
    r.security_id,
    r.date,
    r.ticker,

    tr.resolved_instrument_type
        AS instrument_type,

    tr.resolved_exchange
        AS exchange,

    tr.resolved_isin
        AS isin,

    tr.reference_resolution_status,

    tr.has_active_reference,
    tr.has_delisted_reference,

    CASE
        WHEN tr.resolved_instrument_type = 'Common Stock'
        THEN TRUE
        ELSE FALSE
    END AS common_equity_broad,

    CASE
        WHEN tr.resolved_instrument_type = 'Common Stock'
         AND tr.resolved_exchange IN (
             'NASDAQ',
             'NYSE',
             'AMEX',
             'NYSE MKT'
         )
        THEN TRUE
        ELSE FALSE
    END AS common_equity_primary_exchange,

    r.final_research_eligible
        AS return_research_eligible,

    (
        r.final_research_eligible
        AND tr.resolved_instrument_type = 'Common Stock'
    ) AS primary_research_eligible_broad,

    (
        r.final_research_eligible
        AND tr.resolved_instrument_type = 'Common Stock'
        AND tr.resolved_exchange IN (
            'NASDAQ',
            'NYSE',
            'AMEX',
            'NYSE MKT'
        )
    ) AS primary_research_eligible_exchange

FROM silver.security_daily_return_research r

LEFT JOIN silver.security_ticker_reference_resolution tr
  ON tr.security_id = r.security_id
 AND tr.ticker = r.ticker;
