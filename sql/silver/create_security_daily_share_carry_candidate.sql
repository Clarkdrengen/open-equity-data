-- Research candidate: causal EODHD share carry at 365/540/730 calendar days.
-- The original filed observation and its date are retained for audit. No
-- value is inferred before its filing date or from a later observation.
-- Candidate multi-issue identities are held out of EODHD issuer-total cap.
DROP TABLE IF EXISTS silver.security_daily_share_carry_candidate;

CREATE TABLE silver.security_daily_share_carry_candidate AS
WITH candidate_issues AS (
    SELECT security_id_a AS security_id
    FROM silver.multi_listed_common_equity_candidate
    UNION
    SELECT security_id_b AS security_id
    FROM silver.multi_listed_common_equity_candidate
), factors AS (
    SELECT security_id, date, cumulative_split_multiplier
    FROM silver.security_daily_split_factor_reconciled
), attached AS (
    SELECT p.*, f_now.cumulative_split_multiplier AS current_split_multiplier,
           f_then.cumulative_split_multiplier AS period_split_multiplier,
           (c.security_id IS NOT NULL) AS multi_issue_candidate
    FROM silver.security_daily_shares_outstanding_pit p
    LEFT JOIN factors f_now
      ON f_now.security_id = p.security_id AND f_now.date = p.date
    ASOF LEFT JOIN factors f_then
      ON p.security_id = f_then.security_id
     AND p.shares_period_date >= f_then.date
    LEFT JOIN candidate_issues c ON c.security_id = p.security_id
), classified AS (
    SELECT *,
           CASE
             WHEN shares_outstanding IS NULL THEN 'no_prior_filed_shares'
             WHEN ticker_identity_ambiguous THEN 'ambiguous_ticker_identity'
             WHEN multi_issue_candidate THEN 'multi_issue_issuer_total'
             WHEN shares_age_days > 730 THEN 'older_than_730_days'
             WHEN current_split_multiplier IS NULL OR current_split_multiplier <= 0
                  THEN 'missing_current_split_factor'
             WHEN period_split_multiplier IS NOT NULL AND period_split_multiplier <= 0
                  THEN 'invalid_period_split_factor'
             ELSE 'candidate_usable'
           END AS candidate_status
    FROM attached
)
SELECT security_id, date, ticker, provider_symbol,
       shares_period_date, shares_filing_date, shares_outstanding AS filed_shares,
       shares_source, shares_age_days, ticker_identity_ambiguous,
       multi_issue_candidate, candidate_status,
       current_split_multiplier
         / COALESCE(period_split_multiplier, 1.0) AS split_multiplier_since_period,
       CASE WHEN candidate_status = 'candidate_usable'
            THEN shares_outstanding * current_split_multiplier
               / COALESCE(period_split_multiplier, 1.0)
       END AS estimated_current_shares,
       (candidate_status = 'candidate_usable' AND shares_age_days <= 365)
           AS available_365,
       (candidate_status = 'candidate_usable' AND shares_age_days <= 540)
           AS available_540,
       (candidate_status = 'candidate_usable') AS available_730,
       (candidate_status = 'candidate_usable' AND shares_age_days > 365)
           AS extended_carry
FROM classified;
