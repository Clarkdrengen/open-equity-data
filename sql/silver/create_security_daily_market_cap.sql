-- Raw date-t close times point-in-time shares for the *listed issue*.
-- Missing/ambiguous class shares have no market cap; no issuer-total fallback.

DROP TABLE IF EXISTS silver.security_daily_market_cap;
CREATE TABLE silver.security_daily_market_cap AS
SELECT s.security_id, s.date, s.ticker,
       p.close AS raw_close,
       s.shares_outstanding,
       s.shares_source,
       s.shares_filing_date,
       s.sec_as_of_date,
       s.sec_accession_number,
       s.class_candidate_cik,
       CASE WHEN p.close > 0 AND s.shares_outstanding > 0
            THEN p.close * s.shares_outstanding END AS market_cap,
       p.source AS price_source
FROM silver.security_daily_shares_resolved s
LEFT JOIN silver.security_daily_ohlcv_reconciled p
  ON p.security_id = s.security_id AND p.date = s.date;

-- Use *previous session* market cap to weight the return at t. This is a
-- descriptive benchmark, not an executable trading portfolio.
DROP TABLE IF EXISTS silver.research_market_daily_weighted;
CREATE TABLE silver.research_market_daily_weighted AS
WITH eligible AS (
    SELECT r.date, r.security_id, r.gross_total_return,
           prev.market_cap AS lag_market_cap
    FROM silver.security_daily_return_research r
    JOIN silver.research_universe_eligibility u
      ON u.security_id = r.security_id AND u.date = r.date
    LEFT JOIN silver.security_daily_market_cap prev
      ON prev.security_id = r.security_id AND prev.date = r.previous_date
    WHERE r.final_research_eligible AND u.primary_research_eligible_exchange
)
SELECT date,
       COUNT(*) AS eligible_security_count,
       COUNT(lag_market_cap) AS cap_weighted_security_count,
       AVG(gross_total_return) AS equal_weight_return_full,
       AVG(gross_total_return) FILTER (WHERE lag_market_cap > 0)
           AS equal_weight_return_matched,
       SUM(lag_market_cap * gross_total_return) FILTER (WHERE lag_market_cap > 0)
           / NULLIF(SUM(lag_market_cap) FILTER (WHERE lag_market_cap > 0), 0)
           AS cap_weight_return_matched
FROM eligible
GROUP BY date
ORDER BY date;
