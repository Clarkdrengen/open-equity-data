"""Derive two missing-session price cohorts from archived EODHD bulk bytes.

Bronze remains the exact provider response. Only a unique security/ticker
observed on both adjacent sessions can enter the derived Silver price series.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from open_equity_data.db import connect


ROOT = Path(__file__).resolve().parents[2]
SESSIONS = {
    date(2019, 8, 23): (date(2019, 8, 22), date(2019, 8, 26)),
    date(2019, 9, 17): (date(2019, 9, 16), date(2019, 9, 18)),
}


def _valid_bar(row: dict) -> bool:
    try:
        op, hi, lo, cl = (float(row[key]) for key in ("open", "high", "low", "close"))
        vol = int(row["volume"])
        return 0 < lo <= min(op, cl) <= max(op, cl) <= hi and vol >= 0
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def build(con) -> list[tuple]:
    """Return status counts; all accepted observations remain traceable to Bronze."""
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE bulk_gap_raw (
                date DATE, ticker VARCHAR, provider_code VARCHAR,
                open DOUBLE, high DOUBLE,
                low DOUBLE, close DOUBLE, volume BIGINT,
                response_sha256 VARCHAR, bar_valid BOOLEAN
            )
        """)
        values = []
        for session in SESSIONS:
            before, after = SESSIONS[session]
            bracketed = {ticker for (ticker,) in con.execute("""
                SELECT DISTINCT p.ticker
                FROM silver.security_daily_ohlcv p
                JOIN silver.security_daily_ohlcv n
                  ON n.security_id = p.security_id AND n.ticker = p.ticker
                WHERE p.date = ? AND n.date = ?
            """, [before, after]).fetchall()}
            archived = con.execute("""
                SELECT raw_response_bytes, response_sha256
                FROM bronze.eodhd_bulk_eod_response
                WHERE requested_date = ?
            """, [session]).fetchone()
            if archived is None:
                raise ValueError(f"Missing Bronze EODHD bulk response for {session}")
            raw, digest = bytes(archived[0]), archived[1]
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError(f"Bronze response hash mismatch for {session}")
            rows = json.loads(raw)
            if not isinstance(rows, list) or not rows or any(
                row.get("date") != session.isoformat() for row in rows
            ):
                raise ValueError(f"Unexpected EODHD response date for {session}")
            for row in rows:
                code = row.get("code")
                if not isinstance(code, str):
                    continue
                ticker = code if code in bracketed else code.replace("-", ".")
                if ticker not in bracketed:
                    continue
                valid = _valid_bar(row)
                prices = (
                    tuple(float(row[k]) for k in ("open", "high", "low", "close"))
                    if valid else (None, None, None, None)
                )
                values.append((
                    session, ticker, code, *prices,
                    int(row["volume"]) if valid else None,
                    digest, valid,
                ))
        con.executemany("INSERT INTO bulk_gap_raw VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE bulk_gap_sessions (
                date DATE, before_date DATE, after_date DATE
            )
        """)
        con.executemany(
            "INSERT INTO bulk_gap_sessions VALUES (?, ?, ?)",
            [(day, *neighbors) for day, neighbors in SESSIONS.items()],
        )
        con.execute("""
            CREATE OR REPLACE TABLE silver.eodhd_bulk_missing_price_candidate AS
            WITH provider AS (
                SELECT b.*,
                       COUNT(*) OVER (PARTITION BY b.date, b.ticker)
                           AS provider_rows
                FROM bulk_gap_raw b
            ), adjacent AS (
                SELECT d.date, p.security_id, p.identity_status,
                       p.lineage_id, p.lineage_code, p.ticker,
                       p.close AS before_close, n.close AS after_close,
                       COUNT(*) OVER (PARTITION BY d.date, p.ticker)
                           AS identity_rows
                FROM bulk_gap_sessions d
                JOIN silver.security_daily_ohlcv p
                  ON p.date = d.before_date AND p.research_eligible
                JOIN silver.security_daily_ohlcv n
                  ON n.date = d.after_date AND n.security_id = p.security_id
                 AND n.ticker = p.ticker AND n.research_eligible
                WHERE p.close > 0 AND n.close > 0
                  AND NOT EXISTS (
                    SELECT 1 FROM silver.clean_ohlcv native
                    WHERE native.date = d.date
                      AND native.act_symbol = p.ticker
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM silver.security_daily_ohlcv existing
                    WHERE existing.date = d.date
                      AND existing.security_id = p.security_id
                      AND existing.source_lookup_method
                          IS DISTINCT FROM 'bulk_exact_ticker_adjacent_security'
                  )
            )
            SELECT a.security_id, a.identity_status, a.lineage_id,
                   a.lineage_code, b.date, b.ticker,
                   b.open, b.high, b.low, b.close, b.volume,
                   b.provider_code, b.response_sha256,
                   a.before_close, a.after_close,
                   CASE
                     WHEN b.provider_rows <> 1 THEN 'duplicate_provider_code'
                     WHEN a.identity_rows <> 1 THEN 'ambiguous_security_identity'
                     WHEN NOT b.bar_valid THEN 'invalid_provider_bar'
                     WHEN b.close / a.before_close NOT BETWEEN 0.5 AND 2
                       OR b.close / a.after_close NOT BETWEEN 0.5 AND 2
                       THEN 'price_basis_review'
                     ELSE 'candidate_usable'
                   END AS candidate_status
            FROM adjacent a
            JOIN provider b ON b.date = a.date AND b.ticker = a.ticker
        """)
        summary = con.execute("""
            SELECT date, candidate_status, COUNT(*) AS observations,
                   COUNT(DISTINCT security_id) AS securities
            FROM silver.eodhd_bulk_missing_price_candidate
            GROUP BY ALL ORDER BY date, candidate_status
        """).fetchall()
        con.execute("COMMIT")
        return summary
    except Exception:
        con.execute("ROLLBACK")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Rebuild price, returns, research and market cap Silver tables")
    args = parser.parse_args()
    with connect() as con:
        summary = build(con)
        print("date | status | observations | securities")
        for row in summary:
            print(" | ".join(map(str, row)))
        if not args.apply:
            print("Candidate review only; run with --apply to rebuild dependent Silver tables.")
            return
        from open_equity_data.rebuild_derived_after_identity_fix import FILES, run_file
        from open_equity_data.build_msci_daily_share_preference import build as build_caps

        start = FILES.index("create_security_daily_ohlcv.sql")
        for name in FILES[start:]:
            run_file(con, name)
        build_caps(con)
        for day in SESSIONS:
            print(day, con.execute("""
                SELECT COUNT(*) FILTER (WHERE price_research_eligible),
                       COUNT(*) FILTER (WHERE market_cap_candidate > 0),
                       SUM(market_cap_candidate) / 1e12
                FROM silver.security_daily_market_cap_source_priority_candidate
                WHERE date = ?
            """, [day]).fetchone())


if __name__ == "__main__":
    main()
