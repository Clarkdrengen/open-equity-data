-- Daily market return at t is weighted by market cap at the preceding
-- calendar trading session, never the end-of-return cap at t.
-- Equal-weight returns on exactly the covered members are provided alongside
-- the original all-eligible equal-weight population for comparison.
DROP TABLE IF EXISTS silver.research_market_cap_weighted_candidate;

CREATE TABLE silver.research_market_cap_weighted_candidate AS
WITH eligible AS (
    SELECT r.date, r.security_id, r.gross_total_return,
           c.market_cap_365, c.market_cap_540, c.market_cap_730
    FROM silver.security_daily_return_research r
    JOIN silver.research_universe_eligibility u
      ON u.security_id = r.security_id AND u.date = r.date
    LEFT JOIN silver.security_daily_market_cap_candidate c
      ON c.security_id = r.security_id AND c.date = r.previous_date
    WHERE r.final_research_eligible
      AND u.primary_research_eligible_exchange
)
SELECT date,
       COUNT(*) AS eligible_issues,
       AVG(gross_total_return) AS equal_weight_full_return,
       COUNT(market_cap_365) AS weighted_issues_365,
       COUNT(market_cap_540) AS weighted_issues_540,
       COUNT(market_cap_730) AS weighted_issues_730,
       SUM(market_cap_365) AS total_weight_365,
       SUM(market_cap_540) AS total_weight_540,
       SUM(market_cap_730) AS total_weight_730,
       AVG(gross_total_return) FILTER (WHERE market_cap_365 IS NOT NULL)
           AS equal_weight_covered_365,
       AVG(gross_total_return) FILTER (WHERE market_cap_540 IS NOT NULL)
           AS equal_weight_covered_540,
       AVG(gross_total_return) FILTER (WHERE market_cap_730 IS NOT NULL)
           AS equal_weight_covered_730,
       SUM(market_cap_365 * gross_total_return) / NULLIF(SUM(market_cap_365), 0)
           AS cap_weighted_return_365,
       SUM(market_cap_540 * gross_total_return) / NULLIF(SUM(market_cap_540), 0)
           AS cap_weighted_return_540,
       SUM(market_cap_730 * gross_total_return) / NULLIF(SUM(market_cap_730), 0)
           AS cap_weighted_return_730
FROM eligible
GROUP BY date;
