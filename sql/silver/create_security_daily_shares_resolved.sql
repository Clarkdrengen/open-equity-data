-- Resolve shares conservatively for market-cap work.
-- For simultaneously eligible sibling issues, issuer-total EODHD shares are
-- never used. Only an unambiguous same-filing SEC class/symbol fact may supply
-- class shares. Missing SEC evidence remains missing.

DROP TABLE IF EXISTS silver.sec_class_share_resolved_observation;
CREATE TABLE silver.sec_class_share_resolved_observation AS
WITH issue_symbols AS (
    SELECT DISTINCT cik, UPPER(ticker_a) AS ticker
    FROM silver.multi_listed_common_equity_candidate
    UNION
    SELECT DISTINCT cik, UPPER(ticker_b) AS ticker
    FROM silver.multi_listed_common_equity_candidate
),
facts AS (
    SELECT c.cik, UPPER(c.trading_symbol) AS ticker,
           c.filing_date, c.shares_as_of_date, c.accession_number,
           c.class_member, c.shares_outstanding, c.source_document_sha256
    FROM silver.sec_class_share_candidate c
    JOIN issue_symbols i
      ON i.cik = c.cik AND i.ticker = UPPER(c.trading_symbol)
    WHERE c.symbol_mapping_status = 'mapped_unique_symbol'
      AND c.filing_date IS NOT NULL
      AND c.shares_as_of_date IS NOT NULL
      AND c.shares_as_of_date <= c.filing_date
      AND c.shares_outstanding > 0
),
supported_issuers AS (
    -- At least one filing names two candidate issues and two distinct classes.
    SELECT DISTINCT cik FROM (
        SELECT cik, accession_number
        FROM facts
        GROUP BY cik, accession_number
        HAVING COUNT(DISTINCT ticker) >= 2
           AND COUNT(DISTINCT class_member) >= 2
    ) paired
),
unique_facts AS (
    SELECT f.cik, f.ticker, f.filing_date, f.shares_as_of_date,
           MIN(f.shares_outstanding) AS shares_outstanding,
           MIN(f.accession_number) AS accession_number,
           MIN_BY(f.source_document_sha256, f.accession_number)
               AS source_document_sha256
    FROM facts f
    JOIN supported_issuers s USING (cik)
    GROUP BY f.cik, f.ticker, f.filing_date, f.shares_as_of_date
    HAVING COUNT(DISTINCT f.shares_outstanding) = 1
       AND COUNT(DISTINCT f.class_member) = 1
)
SELECT * FROM unique_facts
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cik, ticker, filing_date
    ORDER BY shares_as_of_date DESC, accession_number DESC
) = 1;

DROP TABLE IF EXISTS silver.security_daily_shares_resolved;
CREATE TABLE silver.security_daily_shares_resolved AS
WITH paired_dates AS (
    -- Actual same-day eligible siblings, not merely overlapping span bounds.
    SELECT p.cik, a.security_id, a.date, UPPER(a.ticker) AS ticker
    FROM silver.multi_listed_common_equity_candidate p
    JOIN silver.research_universe_eligibility a
      ON a.security_id = p.security_id_a AND UPPER(a.ticker) = UPPER(p.ticker_a)
     AND a.date BETWEEN p.overlap_start AND p.overlap_end
     AND a.primary_research_eligible_exchange
    JOIN silver.research_universe_eligibility b
      ON b.security_id = p.security_id_b AND UPPER(b.ticker) = UPPER(p.ticker_b)
     AND b.date = a.date AND b.primary_research_eligible_exchange
    UNION
    SELECT p.cik, b.security_id, b.date, UPPER(b.ticker) AS ticker
    FROM silver.multi_listed_common_equity_candidate p
    JOIN silver.research_universe_eligibility b
      ON b.security_id = p.security_id_b AND UPPER(b.ticker) = UPPER(p.ticker_b)
     AND b.date BETWEEN p.overlap_start AND p.overlap_end
     AND b.primary_research_eligible_exchange
    JOIN silver.research_universe_eligibility a
      ON a.security_id = p.security_id_a AND UPPER(a.ticker) = UPPER(p.ticker_a)
     AND a.date = b.date AND a.primary_research_eligible_exchange
),
class_dates AS (
    SELECT security_id, date, ticker, MIN(cik) AS cik,
           COUNT(DISTINCT cik) AS candidate_ciks
    FROM paired_dates
    GROUP BY security_id, date, ticker
),
sec_pit AS (
    SELECT d.security_id, d.date, o.shares_outstanding,
           o.filing_date, o.shares_as_of_date, o.accession_number,
           o.source_document_sha256
    FROM class_dates d
    ASOF LEFT JOIN silver.sec_class_share_resolved_observation o
      ON d.cik = o.cik AND d.ticker = o.ticker AND d.date >= o.filing_date
    WHERE d.candidate_ciks = 1
),
daily AS (
    SELECT u.security_id, u.date, u.ticker,
           c.cik AS class_candidate_cik,
           c.candidate_ciks,
           e.shares_outstanding AS eodhd_shares,
           e.shares_filing_date AS eodhd_filing_date,
           e.shares_pit_available AS eodhd_available,
           s.shares_outstanding AS sec_shares,
           s.filing_date AS sec_filing_date,
           s.shares_as_of_date AS sec_as_of_date,
           s.accession_number AS sec_accession_number,
           s.source_document_sha256 AS sec_document_sha256
    FROM silver.research_universe_eligibility u
    LEFT JOIN class_dates c ON c.security_id = u.security_id AND c.date = u.date
    LEFT JOIN silver.security_daily_shares_outstanding_pit e
      ON e.security_id = u.security_id AND e.date = u.date
    LEFT JOIN sec_pit s ON s.security_id = u.security_id AND s.date = u.date
    WHERE u.primary_research_eligible_exchange
)
SELECT security_id, date, ticker, class_candidate_cik,
       class_candidate_cik IS NOT NULL AS simultaneous_class_candidate,
       CASE
           WHEN class_candidate_cik IS NOT NULL
            AND candidate_ciks = 1
            AND sec_shares > 0
            AND DATE_DIFF('day', sec_filing_date, date) BETWEEN 0 AND 365
           THEN sec_shares
           WHEN class_candidate_cik IS NULL AND COALESCE(eodhd_available, FALSE)
           THEN eodhd_shares
       END AS shares_outstanding,
       CASE
           WHEN class_candidate_cik IS NOT NULL AND candidate_ciks > 1
           THEN 'ambiguous_candidate_issuer'
           WHEN class_candidate_cik IS NOT NULL AND sec_shares > 0
            AND DATE_DIFF('day', sec_filing_date, date) BETWEEN 0 AND 365
           THEN 'sec_class_filing'
           WHEN class_candidate_cik IS NOT NULL THEN 'missing_sec_class'
           WHEN COALESCE(eodhd_available, FALSE) THEN 'eodhd_issuer_total'
           ELSE 'missing_eodhd_pit'
       END AS shares_source,
       CASE WHEN class_candidate_cik IS NOT NULL THEN sec_filing_date
            ELSE eodhd_filing_date END AS shares_filing_date,
       sec_as_of_date, sec_accession_number, sec_document_sha256
FROM daily;
