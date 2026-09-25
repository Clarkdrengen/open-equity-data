"""
Rebuild derived Silver research state after the security-identity correction.

The following curated / previously validated state is treated as INPUT
and is NOT recreated in this pass:

    silver.corporate_action_override
    silver.automatic_price_correction
    silver.automatic_split_backfill
    silver.automatic_dividend_correction

Everything downstream of security identity is recomputed.

The rebuild deliberately stops before model fitting / benchmark datasets.
"""

from __future__ import annotations

from pathlib import Path
import time

from open_equity_data.db import connect


SQL = Path("sql/silver")


# Dependency order.
#
# Automatic correction tables are intentionally NOT included here:
# they have already been migrated to the corrected security IDs and
# serve as validated inputs to this first canonical rebuild.
FILES = [
    # Identity-dependent price series
    "create_lineage_ohlcv.sql",
    "create_security_daily_ohlcv.sql",

    # Corporate actions: splits
    "create_security_split_candidate.sql",
    "create_split_full_history_comparison.sql",
    "create_security_split_event.sql",
    "create_security_daily_split_factor.sql",
    "create_security_daily_split_factor_reconciled.sql",

    # Corporate actions: dividends
    "create_security_dividend_candidate.sql",
    "create_security_dividend_event.sql",

    # Apply previously validated price corrections
    "create_security_daily_ohlcv_reconciled.sql",

    # Returns
    "create_security_daily_return_basis.sql",
    "create_security_daily_return.sql",

    # Recompute extreme-return diagnostics under corrected identity
    "create_extreme_return_price_comparison.sql",
    "create_extreme_return_diagnostic.sql",

    # Research return quarantine / index
    "create_security_daily_return_research.sql",
    "create_security_gtr_index.sql",

    # Security reference + strict research universe
    "create_security_reference_resolution.sql",

    # PIT shares must inherit corrected security IDs
    "create_security_shares_outstanding_pit.sql",

    # Research features / labels
    "create_research_feature_table.sql",
    "create_research_feature_label_model.sql",
]


def run_file(con, filename: str) -> float:
    path = SQL / filename

    if not path.exists():
        raise FileNotFoundError(path)

    sql = path.read_text()

    print(f"\n▶ {filename}", flush=True)

    t0 = time.time()
    con.execute(sql)
    elapsed = time.time() - t0

    print(
        f"  ✓ {elapsed:.1f}s",
        flush=True,
    )

    return elapsed


def table_count(con, table: str):
    try:
        return con.execute(
            f"""
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT security_id) AS securities
            FROM silver.{table}
            """
        ).fetchone()
    except Exception:
        return None


def main() -> None:
    con = connect()

    started = time.time()

    print("DERIVED SILVER REBUILD")
    print("======================")

    # --------------------------------------------------------
    # Preflight: migrated state must reference current IDs only.
    # --------------------------------------------------------

    print("\nPREFLIGHT")
    print("---------")

    stateful = [
        "corporate_action_override",
        "automatic_price_correction",
        "automatic_split_backfill",
        "automatic_dividend_correction",
    ]

    for table in stateful:
        row = con.execute(
            f"""
            SELECT
                COUNT(*) AS rows,

                COUNT(*) FILTER (
                    WHERE s.security_id IS NULL
                ) AS invalid_security_ids

            FROM silver.{table} t

            LEFT JOIN silver.security_master s
              ON s.security_id = t.security_id
            """
        ).fetchone()

        print(
            f"{table:35s} "
            f"rows={row[0]:6,d} "
            f"invalid_ids={row[1]:3,d}"
        )

        if row[1] != 0:
            raise RuntimeError(
                f"{table} contains "
                f"{row[1]} obsolete security IDs"
            )

    # --------------------------------------------------------
    # Save the old canonical research counts for comparison.
    # These tables still represent the pre-identity-fix stack.
    # --------------------------------------------------------

    baseline_tables = [
        "security_daily_ohlcv",
        "security_daily_ohlcv_reconciled",
        "security_daily_return_basis",
        "security_daily_return",
        "security_daily_return_research",
        "security_gtr_index",
        "research_universe_eligibility",
        "research_feature_label",
        "research_feature_label_model",
    ]

    print("\nPRE-REBUILD COUNTS")
    print("------------------")

    before = {}

    for table in baseline_tables:
        value = table_count(con, table)
        before[table] = value

        print(
            f"{table:40s} {value}"
        )

    # --------------------------------------------------------
    # Rebuild.
    # --------------------------------------------------------

    timings = []

    print("\nREBUILD")
    print("-------")

    for i, filename in enumerate(
        FILES,
        start=1,
    ):
        overall_elapsed = time.time() - started

        print(
            f"\n[{i:02d}/{len(FILES):02d}] "
            f"total elapsed={overall_elapsed:.1f}s",
            flush=True,
        )

        elapsed = run_file(
            con,
            filename,
        )

        timings.append(
            (filename, elapsed)
        )

    # --------------------------------------------------------
    # Post-rebuild counts.
    # --------------------------------------------------------

    print("\nPOST-REBUILD COUNTS")
    print("-------------------")

    after = {}

    for table in baseline_tables:
        value = table_count(con, table)
        after[table] = value

        print(
            f"{table:40s} {value}"
        )

    # --------------------------------------------------------
    # Core structural invariants.
    # --------------------------------------------------------

    print("\nSTRUCTURAL INVARIANTS")
    print("---------------------")

    duplicate_security_dates = con.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                security_id,
                date
            FROM silver.security_daily_ohlcv
            GROUP BY 1,2
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    print(
        "duplicate security/date OHLCV:",
        duplicate_security_dates,
    )

    if duplicate_security_dates != 0:
        raise RuntimeError(
            "Duplicate security/date rows after rebuild"
        )

    orphan_returns = con.execute("""
        SELECT COUNT(*)
        FROM silver.security_daily_return r
        LEFT JOIN silver.security_master s
          ON s.security_id = r.security_id
        WHERE s.security_id IS NULL
    """).fetchone()[0]

    print(
        "return rows with orphan security_id:",
        orphan_returns,
    )

    if orphan_returns != 0:
        raise RuntimeError(
            "Orphan security IDs in return table"
        )

    # --------------------------------------------------------
    # Economic row-coverage comparison.
    #
    # Identity consolidation should mostly change the number of
    # securities, not destroy underlying price rows.
    # --------------------------------------------------------

    old_price_rows = before[
        "security_daily_ohlcv"
    ][0]

    new_price_rows = after[
        "security_daily_ohlcv"
    ][0]

    print(
        "OHLCV row change:",
        f"{old_price_rows:,} -> {new_price_rows:,}",
        f"({new_price_rows - old_price_rows:+,})",
    )

    pct_change = (
        (new_price_rows - old_price_rows)
        / old_price_rows
    )

    print(
        "OHLCV row % change:",
        f"{pct_change:.4%}",
    )

    # Do not demand exact equality because validated lineages may
    # legitimately change gap treatment / reconciliation. But a
    # large change is a stopping condition.
    if abs(pct_change) > 0.01:
        raise RuntimeError(
            "OHLCV row count changed by more than 1%"
        )

    # --------------------------------------------------------
    # Security-count correction.
    # --------------------------------------------------------

    print("\nSECURITY-ID CONSOLIDATION")
    print("-------------------------")

    print(
        "old OHLCV security IDs:",
        before["security_daily_ohlcv"][1],
    )

    print(
        "new OHLCV security IDs:",
        after["security_daily_ohlcv"][1],
    )

    # --------------------------------------------------------
    # Liberty regression test.
    # --------------------------------------------------------

    print("\nLIBERTY REGRESSION TEST")
    print("-----------------------")

    for row in con.execute("""
        SELECT
            ticker,
            COUNT(DISTINCT security_id)
                AS security_ids,
            COUNT(*) AS rows,
            MIN(date),
            MAX(date)
        FROM silver.security_daily_ohlcv
        WHERE ticker IN (
            'LBTYA',
            'LBTYB',
            'LBTYK'
        )
        GROUP BY ticker
        ORDER BY ticker
    """).fetchall():
        print(row)

    # --------------------------------------------------------
    # Explicit ticker-change lineage regression test.
    # --------------------------------------------------------

    print("\nVALIDATED LINEAGE REGRESSION TEST")
    print("---------------------------------")

    for row in con.execute("""
        SELECT
            s.security_id,

            string_agg(
                DISTINCT o.ticker,
                ', '
                ORDER BY o.ticker
            ) AS tickers,

            MIN(o.date),
            MAX(o.date),

            COUNT(*) AS rows

        FROM silver.security_daily_ohlcv o

        JOIN silver.security_master s
          ON s.security_id = o.security_id

        WHERE o.ticker IN (
            'FB',
            'META',
            'KCAP',
            'PTMN',
            'BCIC',
            'RMED',
            'VTAK'
        )

        GROUP BY s.security_id

        ORDER BY s.security_id
    """).fetchall():
        print(row)

    # --------------------------------------------------------
    # Strict universe.
    # --------------------------------------------------------

    print("\nSTRICT RESEARCH UNIVERSE")
    print("------------------------")

    universe = con.execute("""
        SELECT
            COUNT(*) FILTER (
                WHERE primary_research_eligible_exchange
            ) AS rows,

            COUNT(DISTINCT security_id) FILTER (
                WHERE primary_research_eligible_exchange
            ) AS securities,

            COUNT(DISTINCT ticker) FILTER (
                WHERE primary_research_eligible_exchange
            ) AS tickers

        FROM silver.research_universe_eligibility
    """).fetchone()

    print(universe)

    # --------------------------------------------------------
    # PIT shares.
    # --------------------------------------------------------

    print("\nPIT SHARES")
    print("----------")

    shares = con.execute("""
        SELECT
            COUNT(*) AS rows,

            COUNT(*) FILTER (
                WHERE shares_pit_available
            ) AS usable_rows,

            COUNT(DISTINCT security_id)
                AS securities,

            COUNT(DISTINCT security_id)
                FILTER (
                    WHERE shares_pit_available
                ) AS usable_securities

        FROM silver.security_daily_shares_outstanding_pit
    """).fetchone()

    print(shares)

    if shares[0] > 0:
        print(
            "usable row coverage:",
            f"{shares[1] / shares[0]:.2%}",
        )

    # --------------------------------------------------------
    # Timing summary.
    # --------------------------------------------------------

    print("\nTIMINGS")
    print("-------")

    for filename, elapsed in timings:
        print(
            f"{filename:48s} "
            f"{elapsed:8.1f}s"
        )

    print(
        f"\nTOTAL: "
        f"{time.time() - started:.1f}s"
    )

    con.close()


if __name__ == "__main__":
    main()
