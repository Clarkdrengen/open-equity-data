from open_equity_data.db import connect


COMPONENT_SQL = """
WITH RECURSIVE

edges AS (
    SELECT from_episode_id AS a, to_episode_id AS b
    FROM silver.ticker_transition
    WHERE same_security = TRUE

    UNION ALL

    SELECT to_episode_id AS a, from_episode_id AS b
    FROM silver.ticker_transition
    WHERE same_security = TRUE
),

nodes AS (
    SELECT a AS episode_id FROM edges
    UNION
    SELECT b AS episode_id FROM edges
),

reach(root_episode_id, episode_id) AS (
    SELECT episode_id, episode_id
    FROM nodes

    UNION

    SELECT
        r.root_episode_id,
        e.b
    FROM reach r
    JOIN edges e
      ON e.a = r.episode_id
),

components AS (
    SELECT
        episode_id,
        MIN(root_episode_id) AS component_root
    FROM reach
    GROUP BY episode_id
)

SELECT
    c.component_root,
    e.ticker_episode_id,
    e.act_symbol,
    e.start_date,
    e.end_date
FROM components c
JOIN silver.ticker_episode e
  ON e.ticker_episode_id = c.episode_id
ORDER BY c.component_root, e.start_date
"""


def next_lineage_code(con, ticker: str) -> str:
    existing = con.execute(
        """
        SELECT lineage_code
        FROM silver.ticker_lineage_master
        WHERE lineage_code LIKE ?
        """,
        [f"{ticker}_%"],
    ).fetchall()

    used = set()

    for (code,) in existing:
        try:
            used.add(int(code.rsplit("_", 1)[1]))
        except (ValueError, IndexError):
            pass

    suffix = 1
    while suffix in used:
        suffix += 1

    return f"{ticker}_{suffix}"


def main():
    con = connect()

    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.lineage_reconciliation_log (
            reconciliation_id BIGINT,
            component_root VARCHAR,
            action VARCHAR,
            lineage_id BIGINT,
            lineage_code VARCHAR,
            episode_count INTEGER,
            reconciled_at TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS silver.lineage_reconciliation_issue (
            component_root VARCHAR,
            issue_type VARCHAR,
            existing_lineage_ids VARCHAR,
            detected_at TIMESTAMP
        )
    """)

    rows = con.execute(COMPONENT_SQL).fetchall()

    components = {}

    for component_root, episode_id, ticker, start_date, end_date in rows:
        components.setdefault(component_root, []).append({
            "episode_id": episode_id,
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
        })

    con.execute("BEGIN TRANSACTION")

    try:
        for component_root, episodes in components.items():
            episode_ids = [x["episode_id"] for x in episodes]

            placeholders = ",".join(["?"] * len(episode_ids))

            existing = con.execute(
                f"""
                SELECT DISTINCT lineage_id
                FROM silver.ticker_lineage_membership
                WHERE ticker_episode_id IN ({placeholders})
                """,
                episode_ids,
            ).fetchall()

            lineage_ids = sorted(row[0] for row in existing)

            latest = max(
                episodes,
                key=lambda x: (x["end_date"], x["start_date"]),
            )

            first_date = min(x["start_date"] for x in episodes)
            last_date = max(x["end_date"] for x in episodes)
            latest_ticker = latest["ticker"]

            if len(lineage_ids) > 1:
                con.execute(
                    """
                    INSERT INTO silver.lineage_reconciliation_issue
                    VALUES (?, 'MULTIPLE_EXISTING_LINEAGES', ?, CURRENT_TIMESTAMP)
                    """,
                    [
                        component_root,
                        ",".join(str(x) for x in lineage_ids),
                    ],
                )

                print(
                    "REVIEW:",
                    component_root,
                    "contains lineage IDs",
                    lineage_ids,
                )
                continue

            if len(lineage_ids) == 1:
                lineage_id = lineage_ids[0]

                lineage_code = con.execute(
                    """
                    SELECT lineage_code
                    FROM silver.ticker_lineage_master
                    WHERE lineage_id = ?
                    """,
                    [lineage_id],
                ).fetchone()[0]

                action = "REUSE_EXISTING_LINEAGE"

            else:
                lineage_code = next_lineage_code(
                    con,
                    latest_ticker,
                )

                lineage_id = con.execute(
                    """
                    SELECT nextval('silver.lineage_id_seq')
                    """
                ).fetchone()[0]

                con.execute(
                    """
                    INSERT INTO silver.ticker_lineage_master
                    VALUES (
                        ?, ?, ?, ?, ?,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """,
                    [
                        lineage_id,
                        lineage_code,
                        latest_ticker,
                        first_date,
                        last_date,
                    ],
                )

                action = "CREATE_NEW_LINEAGE"

            for sequence_number, episode in enumerate(episodes, start=1):
                exists = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM silver.ticker_lineage_membership
                    WHERE lineage_id = ?
                      AND ticker_episode_id = ?
                    """,
                    [
                        lineage_id,
                        episode["episode_id"],
                    ],
                ).fetchone()[0]

                if not exists:
                    con.execute(
                        """
                        INSERT INTO silver.ticker_lineage_membership
                        VALUES (?, ?, ?)
                        """,
                        [
                            lineage_id,
                            episode["episode_id"],
                            sequence_number,
                        ],
                    )

            con.execute(
                """
                UPDATE silver.ticker_lineage_master
                SET latest_ticker = ?,
                    first_observed_date = ?,
                    last_observed_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lineage_id = ?
                """,
                [
                    latest_ticker,
                    first_date,
                    last_date,
                    lineage_id,
                ],
            )

            reconciliation_id = con.execute(
                """
                SELECT COALESCE(MAX(reconciliation_id), 0) + 1
                FROM silver.lineage_reconciliation_log
                """
            ).fetchone()[0]

            con.execute(
                """
                INSERT INTO silver.lineage_reconciliation_log
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    reconciliation_id,
                    component_root,
                    action,
                    lineage_id,
                    lineage_code,
                    len(episodes),
                ],
            )

            print(
                action,
                lineage_id,
                lineage_code,
                episode_ids,
            )

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    con.close()


if __name__ == "__main__":
    main()
