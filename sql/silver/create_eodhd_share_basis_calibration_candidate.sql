-- Infer a vendor share basis from *dated* MSCI overlap, not from a later
-- universe membership. This table is evidence for the EODHD fallback only.
CREATE OR REPLACE TABLE silver.eodhd_share_basis_calibration_candidate AS
WITH overlap AS (
    SELECT s.security_id, s.ticker, s.observation_date,
           s.rif_closing_shares AS msci_shares,
           s.anchor_split_multiplier AS snapshot_factor,
           f.cumulative_split_multiplier AS final_factor,
           o.shares_outstanding AS eodhd_shares,
           o.filing_date
    FROM silver.msci_preferred_share_snapshot_candidate s
    ASOF LEFT JOIN silver.security_shares_outstanding_effective o
      ON s.ticker = o.ticker AND s.observation_date >= o.filing_date
    ASOF LEFT JOIN silver.security_daily_split_factor_reconciled f
      ON s.security_id = f.security_id
     AND CAST(o.retrieved_at AS DATE) >= f.date
), evidence AS (
    SELECT *, eodhd_shares / msci_shares AS source_ratio,
           final_factor / snapshot_factor AS later_split_ratio
    FROM overlap
    WHERE eodhd_shares > 0 AND msci_shares > 0
      AND date_diff('day', filing_date, observation_date) BETWEEN 0 AND 365
      AND final_factor > 0 AND snapshot_factor > 0
), scored AS (
    SELECT security_id,
           COUNT(*) AS comparable_snapshots,
           COUNT(*) FILTER (
               WHERE (later_split_ratio >= 1.5 OR later_split_ratio <= 1.0 / 1.5)
                 AND ABS(LN(source_ratio / later_split_ratio)) <= LN(1.25)
           ) AS retrospective_hits,
           COUNT(*) FILTER (
               WHERE (later_split_ratio >= 1.5 OR later_split_ratio <= 1.0 / 1.5)
                 AND ABS(LN(source_ratio)) <= LN(1.25)
           ) AS contemporaneous_hits,
           COUNT(*) FILTER (
               WHERE ABS(LN(source_ratio)) > LN(1.5)
                 AND ABS(LN(source_ratio / later_split_ratio)) > LN(1.5)
           ) AS conflicting_hits
    FROM evidence
    GROUP BY security_id
)
SELECT security_id, comparable_snapshots, retrospective_hits,
       contemporaneous_hits, conflicting_hits,
       CASE WHEN retrospective_hits >= 2 AND contemporaneous_hits = 0
                     AND conflicting_hits = 0 THEN 'retrospective_confirmed'
            WHEN contemporaneous_hits >= 2 AND retrospective_hits = 0
                     AND conflicting_hits = 0 THEN 'contemporaneous_confirmed'
            WHEN conflicting_hits > 0 THEN 'cross_source_conflict'
            ELSE 'unverified' END AS calibration_status
FROM scored;
