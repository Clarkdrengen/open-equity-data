-- ============================================================
-- Simultaneously listed common-equity issue candidates
--
-- Purpose:
-- Identify issuers for which more than one DISTINCT listed
-- common-equity issue is present simultaneously in the strict
-- research universe.
--
-- This is a candidate layer only.
--
-- SEC current ticker -> CIK mappings are evidence used to group
-- potential sibling issues. They are NOT themselves sufficient
-- to conclude that an issuer has multiple common-equity classes.
--
-- Final classification belongs in a later Silver resolution layer.
-- ============================================================

DROP TABLE IF EXISTS silver.multi_listed_common_equity_candidate;

CREATE TABLE silver.multi_listed_common_equity_candidate AS

WITH issue_span AS (
    SELECT
        u.security_id,
        UPPER(u.ticker) AS ticker,
        MIN(u.date) AS first_date,
        MAX(u.date) AS last_date,
        COUNT(*) AS research_rows

    FROM silver.research_universe_eligibility u

    WHERE u.primary_research_eligible_exchange

    GROUP BY
        u.security_id,
        UPPER(u.ticker)
),

sec_ticker_map AS (
    SELECT DISTINCT
        s.cik,
        UPPER(s.ticker) AS ticker,
        s.exchange

    FROM bronze.sec_submission_ticker s

    WHERE s.cik IS NOT NULL
      AND s.ticker IS NOT NULL
),

mapped_issue AS (
    SELECT
        i.security_id,
        i.ticker,
        i.first_date,
        i.last_date,
        i.research_rows,

        s.cik,
        s.exchange AS sec_exchange

    FROM issue_span i

    JOIN sec_ticker_map s
      ON s.ticker = i.ticker
),

overlapping_pairs AS (
    SELECT
        a.cik,

        a.security_id AS security_id_a,
        a.ticker AS ticker_a,
        a.first_date AS first_date_a,
        a.last_date AS last_date_a,
        a.research_rows AS research_rows_a,

        b.security_id AS security_id_b,
        b.ticker AS ticker_b,
        b.first_date AS first_date_b,
        b.last_date AS last_date_b,
        b.research_rows AS research_rows_b,

        GREATEST(
            a.first_date,
            b.first_date
        ) AS overlap_start,

        LEAST(
            a.last_date,
            b.last_date
        ) AS overlap_end

    FROM mapped_issue a

    JOIN mapped_issue b
      ON a.cik = b.cik
     AND a.security_id < b.security_id
     AND a.first_date <= b.last_date
     AND b.first_date <= a.last_date
)

SELECT
    p.*,

    DATE_DIFF(
        'day',
        p.overlap_start,
        p.overlap_end
    ) + 1 AS overlap_calendar_days

FROM overlapping_pairs p;
