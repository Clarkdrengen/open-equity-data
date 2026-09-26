-- Price and split-adjusted PIT shares are both measured at the same close.
-- Only the EODHD single-issue share candidate is represented in this table.
DROP TABLE IF EXISTS silver.security_daily_market_cap_candidate;

CREATE TABLE silver.security_daily_market_cap_candidate AS
WITH joined AS (
    SELECT s.security_id, s.date, s.ticker,
           s.shares_period_date, s.shares_filing_date, s.shares_age_days,
           s.shares_source, s.candidate_status AS share_status,
           s.estimated_current_shares,
           s.available_365, s.available_540, s.available_730,
           p.close, p.source AS price_source,
           p.research_eligible AS price_research_eligible
    FROM silver.security_daily_share_carry_candidate s
    LEFT JOIN silver.security_daily_ohlcv_reconciled p
      ON p.security_id = s.security_id AND p.date = s.date
)
SELECT *,
       CASE WHEN close IS NULL OR close <= 0 OR NOT COALESCE(price_research_eligible, FALSE)
            THEN 'missing_eligible_price'
            ELSE share_status END AS market_cap_status,
       CASE WHEN close > 0 AND price_research_eligible AND available_365
            THEN close * estimated_current_shares END AS market_cap_365,
       CASE WHEN close > 0 AND price_research_eligible AND available_540
            THEN close * estimated_current_shares END AS market_cap_540,
       CASE WHEN close > 0 AND price_research_eligible AND available_730
            THEN close * estimated_current_shares END AS market_cap_730
FROM joined;
