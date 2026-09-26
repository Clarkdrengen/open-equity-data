"""Read-only provenance check for impossible candidate market capitalizations."""

from open_equity_data.db import connect


ANCHORS = """
    VALUES
      ('CEO', DATE '2011-01-04'),
      ('GLSPT', DATE '2022-03-21'),
      ('GLSPT', DATE '2022-07-13'),
      ('NVDA', DATE '2024-07-03'),
      ('NVDA', DATE '2026-09-11'),
      ('NFLX', DATE '2025-01-22'),
      ('NFLX', DATE '2025-12-04')
"""


def print_query(con, title: str, query: str) -> None:
    result = con.execute(query)
    print(f"\n{title}")
    print(" | ".join(column[0] for column in result.description))
    for row in result.fetchall():
        print(" | ".join("-" if value is None else str(value) for value in row))


def main() -> None:
    with connect(read_only=True) as con:
        print_query(con, "ANCHOR ROWS (cap = price x adjusted shares)", f"""
            WITH anchors(ticker, date) AS ({ANCHORS})
            SELECT c.ticker, c.date, c.security_id,
                   u.instrument_type, u.exchange,
                   COALESCE(n.name, b.security_name) AS reference_name,
                   c.close, s.filed_shares, s.shares_period_date,
                   s.shares_filing_date, s.shares_age_days,
                   s.split_multiplier_since_period,
                   s.estimated_current_shares,
                   c.market_cap_540, c.price_source, s.shares_source
            FROM anchors a
            JOIN silver.security_daily_market_cap_candidate c
              ON c.ticker = a.ticker AND c.date = a.date
            JOIN silver.security_daily_share_carry_candidate s
              ON s.security_id = c.security_id AND s.date = c.date
            LEFT JOIN silver.research_universe_eligibility u
              ON u.security_id = c.security_id AND u.date = c.date
            LEFT JOIN silver.security_symbol_fallback b
              ON b.ticker = c.ticker
            LEFT JOIN LATERAL (
                SELECT name
                FROM silver.security_reference_candidate e
                WHERE e.security_id = c.security_id AND e.ticker = c.ticker
                ORDER BY (e.candidate_method = 'exact_code') DESC, name
                LIMIT 1
            ) n ON TRUE
            ORDER BY c.ticker, c.date, c.security_id
        """)
        print_query(con, "BRONZE EODHD OBSERVATIONS BEHIND ANCHORS", f"""
            WITH anchors(ticker, date) AS ({ANCHORS})
            SELECT c.ticker, c.date, o.provider_symbol, o.period_date,
                   o.filing_date, o.common_stock_shares_outstanding,
                   o.currency_symbol, o.retrieved_at
            FROM anchors a
            JOIN silver.security_daily_market_cap_candidate c
              ON c.ticker = a.ticker AND c.date = a.date
            JOIN silver.security_daily_share_carry_candidate s
              ON s.security_id = c.security_id AND s.date = c.date
            LEFT JOIN bronze.eodhd_fundamental_balance_sheet_observation o
              ON o.ticker = c.ticker
             AND o.period_date = s.shares_period_date
             AND o.filing_date = s.shares_filing_date
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY c.ticker, c.date, c.security_id
                ORDER BY o.retrieved_at DESC NULLS LAST
            ) = 1
            ORDER BY c.ticker, c.date
        """)
        print_query(con, "SPLIT EVENTS FOR THESE TICKERS", """
            SELECT ticker, split_date, split_ratio,
                   validation_source, validation_method
            FROM silver.security_split_event
            WHERE ticker IN ('CEO', 'GLSPT', 'NVDA', 'NFLX')
            ORDER BY ticker, split_date
        """)


if __name__ == "__main__":
    main()
