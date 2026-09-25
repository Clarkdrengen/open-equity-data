"""
Rebuild security identity after removal of observation-gap episode splitting.

Identity principle
------------------
A gap in observed trading does not imply a new security.

ticker_episode now represents one observed ticker history. Explicit
same-security ticker-transition evidence can join multiple ticker histories
into one security lineage.

Security identity is therefore based on:
    1. continuous ticker identity by default;
    2. explicit validated same-security ticker changes;
    3. stable identifier conflicts as a reason NOT to merge.

Observation gaps remain diagnostics only.
"""

from pathlib import Path
import time

from open_equity_data.db import connect


SQL_DIR = Path("sql/silver")


def run_file(con, filename: str) -> None:
    path = SQL_DIR / filename
    sql = path.read_text()

    print(f"\n{filename}", flush=True)

    t0 = time.time()

    con.execute(sql)

    print(
        f"  done in {time.time() - t0:.2f}s",
        flush=True,
    )


def main() -> None:
    con = connect()

    started = time.time()

    # --------------------------------------------------------
    # Preserve the pre-fix identity objects for auditability.
    # --------------------------------------------------------

    print("Creating pre-fix identity snapshots...", flush=True)

    for source, backup in [
        (
            "silver.security_master",
            "silver.security_master_pre_gap_fix",
        ),
        (
            "silver.security_episode_membership",
            "silver.security_episode_membership_pre_gap_fix",
        ),
        (
            "silver.ticker_lineage_master",
            "silver.ticker_lineage_master_pre_gap_fix",
        ),
        (
            "silver.ticker_lineage_membership",
            "silver.ticker_lineage_membership_pre_gap_fix",
        ),
    ]:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {backup}
            AS SELECT * FROM {source}
            """
        )

    # --------------------------------------------------------
    # ticker_episode has already been rebuilt from the corrected
    # SQL, but execute it again so this script is reproducible.
    # --------------------------------------------------------

    run_file(
        con,
        "create_ticker_episode.sql",
    )

    # --------------------------------------------------------
    # Re-materialize explicit cross-ticker transitions against
    # the new one-episode-per-ticker representation.
    # --------------------------------------------------------

    run_file(
        con,
        "create_ticker_transition.sql",
    )

    run_file(
        con,
        "create_ticker_lineage_preview.sql",
    )

    # --------------------------------------------------------
    # Rebuild lineage identity from scratch.
    # Old memberships reference obsolete gap-generated episode IDs.
    # --------------------------------------------------------

    print("\nResetting lineage master...", flush=True)

    con.execute("""
        DROP TABLE IF EXISTS
            silver.ticker_lineage_membership
    """)

    con.execute("""
        DROP TABLE IF EXISTS
            silver.ticker_lineage_master
    """)

    con.execute("""
        DROP SEQUENCE IF EXISTS
            silver.lineage_id_seq
    """)

    run_file(
        con,
        "create_ticker_lineage_master.sql",
    )

    run_file(
        con,
        "bootstrap_ticker_lineage_master.sql",
    )

    # --------------------------------------------------------
    # Rebuild security master from corrected ticker histories.
    # --------------------------------------------------------

    print("\nResetting security master...", flush=True)

    con.execute("""
        DROP TABLE IF EXISTS
            silver.security_episode_membership
    """)

    con.execute("""
        DROP TABLE IF EXISTS
            silver.security_master
    """)

    con.execute("""
        DROP SEQUENCE IF EXISTS
            silver.security_id_seq
    """)

    run_file(
        con,
        "create_security_master.sql",
    )

    run_file(
        con,
        "bootstrap_security_master.sql",
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    print("\nIDENTITY REBUILD VALIDATION")
    print("---------------------------")

    print(
        "Ticker episodes:",
        con.execute("""
            SELECT COUNT(*)
            FROM silver.ticker_episode
        """).fetchone()[0],
    )

    print(
        "Lineages:",
        con.execute("""
            SELECT COUNT(*)
            FROM silver.ticker_lineage_master
        """).fetchone()[0],
    )

    print(
        "Security IDs:",
        con.execute("""
            SELECT COUNT(*)
            FROM silver.security_master
        """).fetchone()[0],
    )

    print(
        "Episode memberships:",
        con.execute("""
            SELECT COUNT(*)
            FROM silver.security_episode_membership
        """).fetchone()[0],
    )

    print("\nMEMBERSHIP INVARIANTS")

    print(
        con.execute("""
            SELECT
                COUNT(*) AS episodes,
                COUNT(DISTINCT ticker_episode_id)
                    AS assigned_episodes,
                COUNT(DISTINCT security_id)
                    AS security_ids
            FROM silver.security_episode_membership
        """).fetchone()
    )

    duplicates = con.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                ticker_episode_id
            FROM silver.security_episode_membership
            GROUP BY ticker_episode_id
            HAVING COUNT(*) <> 1
        )
    """).fetchone()[0]

    print(
        "Episodes assigned != once:",
        duplicates,
    )

    unassigned = con.execute("""
        SELECT COUNT(*)
        FROM silver.ticker_episode e
        LEFT JOIN silver.security_episode_membership m
          ON m.ticker_episode_id = e.ticker_episode_id
        WHERE m.ticker_episode_id IS NULL
    """).fetchone()[0]

    print(
        "Unassigned episodes:",
        unassigned,
    )

    print("\nLIBERTY GLOBAL")

    for row in con.execute("""
        SELECT
            e.act_symbol,
            m.security_id,
            s.identity_status,
            s.lineage_id,
            e.start_date,
            e.end_date,
            e.n_observations,
            e.max_internal_gap_days,
            e.gaps_over_7_days,
            e.gaps_over_30_days
        FROM silver.ticker_episode e

        JOIN silver.security_episode_membership m
          ON m.ticker_episode_id = e.ticker_episode_id

        JOIN silver.security_master s
          ON s.security_id = m.security_id

        WHERE e.act_symbol IN (
            'LBTYA',
            'LBTYB',
            'LBTYK'
        )

        ORDER BY e.act_symbol
    """).fetchall():
        print(row)

    print(
        f"\nCompleted in "
        f"{time.time() - started:.1f}s"
    )

    con.close()


if __name__ == "__main__":
    main()
