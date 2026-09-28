"""Populate dated GLSPT subunit-share evidence and rebuild the cap candidate.

Run without --apply to inspect the exact rows; --apply writes Bronze and
rebuilds dependent Silver in one transaction. Only priced GLSPT sessions
through its Nasdaq last-trading date are in scope.
"""

from __future__ import annotations

import argparse

from open_equity_data.build_msci_daily_share_preference import (
    MANUAL_SCHEMA,
    build,
)
from open_equity_data.db import connect


SOURCE_SQL = """
CREATE OR REPLACE TEMP TABLE glspt_manual_stage AS
WITH sources AS (
    SELECT * FROM (VALUES
        (DATE '2021-04-14', DATE '2021-04-14', 16750000.0,
         '0001213900-21-021574',
         'https://www.sec.gov/Archives/edgar/data/1821169/000121390021021574/ea139466-8k_globalspac.htm',
         '16,000,000 IPO units and 750,000 additional units; one subunit per unit'),
        (DATE '2022-04-15', DATE '2022-04-11', 12948213.0,
         '0001213900-22-019951',
         'https://www.sec.gov/Archives/edgar/data/1821169/000121390022019951/ea158437-8k_globalspac.htm',
         '3,801,787 public subunits redeemed; 12,948,213 remained')
    ) AS s(publication_date, as_of_date, shares, document_id,
           document_url, source_excerpt)
), priced AS (
    SELECT p.security_id, p.ticker, p.date AS price_date
    FROM silver.security_daily_ohlcv_reconciled p
    WHERE p.ticker = 'GLSPT'
      AND p.date BETWEEN DATE '2021-05-10' AND DATE '2022-07-13'
      AND EXISTS (
          SELECT 1 FROM silver.security_ticker_reference_resolution r
          WHERE r.security_id = p.security_id AND r.ticker = p.ticker
            AND upper(r.bronze_security_name) LIKE '%GLOBAL SPAC PARTNERS%'
      )
)
SELECT p.security_id, p.ticker, p.price_date,
       o.provider_symbol AS target_provider_symbol,
       o.period_date AS target_period_date,
       o.filing_date AS target_filing_date,
       o.shares_outstanding AS target_shares,
       s.shares AS sourced_shares, s.as_of_date AS shares_as_of_date,
       s.publication_date AS source_publication_date,
       'SEC filing' AS source_name, s.document_url AS source_url,
       s.document_id AS source_document_id, s.source_excerpt
FROM priced p
JOIN sources s
  ON p.price_date >= s.publication_date
 AND date_diff('day', s.publication_date, p.price_date) BETWEEN 0 AND 365
ASOF LEFT JOIN silver.security_shares_outstanding_effective o
  ON p.ticker = o.ticker AND p.price_date >= o.filing_date
QUALIFY row_number() OVER (
    PARTITION BY p.security_id, p.price_date
    ORDER BY s.publication_date DESC
) = 1
"""


def stage(con):
    con.execute(SOURCE_SQL)
    missing = con.execute("""
        SELECT COUNT(*) FROM silver.security_daily_ohlcv_reconciled p
        WHERE p.ticker = 'GLSPT'
          AND p.date BETWEEN DATE '2021-05-10' AND DATE '2022-07-13'
          AND NOT EXISTS (
              SELECT 1 FROM glspt_manual_stage s
              WHERE s.security_id = p.security_id AND s.price_date = p.date
          )
    """).fetchone()[0]
    summary = con.execute("""
        SELECT source_document_id, sourced_shares, COUNT(*) AS stock_dates,
               MIN(price_date), MAX(price_date), COUNT(DISTINCT security_id)
        FROM glspt_manual_stage
        GROUP BY 1, 2 ORDER BY 4
    """).fetchall()
    last = con.execute("""
        SELECT security_id, price_date, sourced_shares, target_shares,
               source_document_id
        FROM glspt_manual_stage WHERE price_date = DATE '2022-07-13'
    """).fetchall()
    if missing or not summary or not last:
        raise ValueError(
            f"GLSPT price coverage mismatch: missing={missing}, "
            f"source_periods={len(summary)}, last_date_rows={len(last)}"
        )
    return summary, last


def apply(con):
    existing = con.execute("""
        SELECT COUNT(*) FROM bronze.eodhd_share_manual_adjustment
        WHERE ticker = 'GLSPT'
          AND source_document_id NOT IN
              ('0001213900-21-021574', '0001213900-22-019951')
    """).fetchone()[0]
    if existing:
        raise ValueError(f"GLSPT has {existing} other manual rows; review first")
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("""
            DELETE FROM bronze.eodhd_share_manual_adjustment
            WHERE ticker = 'GLSPT'
              AND source_document_id IN
                  ('0001213900-21-021574', '0001213900-22-019951')
        """)
        con.execute("""
            INSERT INTO bronze.eodhd_share_manual_adjustment (
                security_id, ticker, target_provider_symbol,
                target_period_date, target_filing_date, target_shares,
                sourced_shares, shares_as_of_date, source_publication_date,
                source_name, source_url, source_document_id, source_excerpt,
                source_document_sha256, recorded_at, price_date
            )
            SELECT security_id, ticker, target_provider_symbol,
                   target_period_date, target_filing_date, target_shares,
                   sourced_shares, shares_as_of_date,
                   source_publication_date, source_name, source_url,
                   source_document_id, source_excerpt, NULL,
                   current_timestamp, price_date
            FROM glspt_manual_stage
        """)
        build(con, manage_transaction=False)
        result = con.execute("""
            SELECT date, security_id, ticker, selected_source,
                   selected_shares_candidate, close, market_cap_candidate
            FROM silver.security_daily_market_cap_source_priority_candidate
            WHERE ticker = 'GLSPT' AND date = DATE '2022-07-13'
        """).fetchall()
        con.execute("COMMIT")
        return result
    except Exception:
        con.execute("ROLLBACK")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        con.execute(MANUAL_SCHEMA.read_text())
        summary, last = stage(con)
        print("source_document | sourced_shares | stock_dates | first | last | issues")
        for row in summary:
            print(row)
        print("Last trading day staged:", last)
        if args.apply:
            print("Rebuilt GLSPT daily candidate:", apply(con))
        else:
            print("Preview only. Run with --apply to populate Bronze and rebuild Silver.")


if __name__ == "__main__":
    main()
