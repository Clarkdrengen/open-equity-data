-- Aggregate outstanding equity value of covered primary-exchange issues.
-- Changes in membership or filed-share availability change this level.
-- This is NOT a portfolio total-return or broad-market index.
DROP TABLE IF EXISTS silver.research_aggregate_market_cap_index_candidate;

CREATE TABLE silver.research_aggregate_market_cap_index_candidate AS
WITH daily AS (
    SELECT date, COUNT(*) AS eligible_issues,
           COUNT(market_cap_365) AS covered_issues_365,
           COUNT(market_cap_540) AS covered_issues_540,
           COUNT(market_cap_730) AS covered_issues_730,
           SUM(market_cap_365) AS aggregate_cap_365,
           SUM(market_cap_540) AS aggregate_cap_540,
           SUM(market_cap_730) AS aggregate_cap_730
    FROM silver.security_daily_market_cap_candidate
    GROUP BY date
), first_common AS (
    SELECT MIN(date) AS base_date
    FROM daily
    WHERE aggregate_cap_365 > 0
      AND aggregate_cap_540 > 0
      AND aggregate_cap_730 > 0
), base AS (
    SELECT d.base_date, b.aggregate_cap_365 AS base_cap_365,
           b.aggregate_cap_540 AS base_cap_540,
           b.aggregate_cap_730 AS base_cap_730
    FROM first_common d
    LEFT JOIN daily b ON b.date = d.base_date
)
SELECT d.*, b.base_date,
       covered_issues_365::DOUBLE / eligible_issues AS issue_coverage_365,
       covered_issues_540::DOUBLE / eligible_issues AS issue_coverage_540,
       covered_issues_730::DOUBLE / eligible_issues AS issue_coverage_730,
       CASE WHEN d.date >= b.base_date
            THEN 100.0 * d.aggregate_cap_365 / b.base_cap_365 END AS cap_index_365,
       CASE WHEN d.date >= b.base_date
            THEN 100.0 * d.aggregate_cap_540 / b.base_cap_540 END AS cap_index_540,
       CASE WHEN d.date >= b.base_date
            THEN 100.0 * d.aggregate_cap_730 / b.base_cap_730 END AS cap_index_730
FROM daily d CROSS JOIN base b
ORDER BY d.date;
