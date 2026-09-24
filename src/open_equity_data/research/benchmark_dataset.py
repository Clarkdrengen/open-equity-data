"""
Reproducible model-ready datasets for the technical return benchmark.

Important research rules
------------------------
1. Model development uses train + validation only.
2. The 2025+ test sample is deliberately not exposed by this module.
3. Sampling is deterministic and does not depend on the target class.
4. Training observations are distributed across calendar years so later
   years with a larger listed universe do not completely dominate training.
5. The same feature specification is used for every prediction horizon.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from open_equity_data.db import connect


HORIZONS = (1, 5, 10, 20, 60)

FEATURES = (
    "lag_1d_gtr",

    "trailing_gtr_14d",
    "trailing_gtr_20d",
    "trailing_gtr_60d",

    "realized_vol_14d",
    "realized_vol_20d",
    "realized_vol_60d",

    "scaled_lag_1d_return_14d",
    "scaled_lag_1d_return_20d",
    "scaled_lag_1d_return_60d",

    "rsi_14",
    "rsi_20",
    "rsi_60",

    "relative_volume_14d",
    "relative_volume_20d",
    "relative_volume_60d",

    "volume_zscore_14d",
    "volume_zscore_20d",
    "volume_zscore_60d",

    "market_return_1d",
    "market_relative_return_1d",
)

ID_COLUMNS = (
    "security_id",
    "date",
    "ticker",
)

DEFAULT_OUTPUT_DIR = Path(
    "artifacts/research/benchmark_v1/datasets"
)

DEFAULT_TABPFN_TRAIN_ROWS = 100_000
DEFAULT_LARGE_TRAIN_ROWS = 1_000_000
DEFAULT_VALIDATION_ROWS = 250_000

SAMPLING_SEED = "open_equity_data_benchmark_v1"


@dataclass(frozen=True)
class DatasetSpec:
    horizon: int

    @property
    def target_column(self) -> str:
        return f"target_outperform_{self.horizon}d"

    @property
    def return_column(self) -> str:
        return f"forward_rel_return_{self.horizon}d"

    @property
    def split_column(self) -> str:
        return f"split_{self.horizon}d"

    @property
    def target_end_date_column(self) -> str:
        return f"target_end_date_{self.horizon}d"


def _sql_identifier_list(columns: Iterable[str]) -> str:
    return ",\n        ".join(columns)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _path_literal(path: Path) -> str:
    return _sql_literal(str(path.resolve()))


def _feature_complete_predicate() -> str:
    return "\n      AND ".join(
        f"{feature} IS NOT NULL"
        for feature in FEATURES
    )


def validate_source_table(con) -> None:
    """
    Fail loudly if the benchmark table or expected columns are missing.
    """

    exists = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'silver'
          AND table_name = 'research_feature_label_model'
    """).fetchone()[0]

    if not exists:
        raise RuntimeError(
            "silver.research_feature_label_model does not exist"
        )

    actual_columns = {
        row[0]
        for row in con.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'silver'
              AND table_name = 'research_feature_label_model'
        """).fetchall()
    }

    required = set(ID_COLUMNS) | set(FEATURES)

    for horizon in HORIZONS:
        spec = DatasetSpec(horizon)
        required.update(
            {
                spec.target_column,
                spec.return_column,
                spec.split_column,
                spec.target_end_date_column,
            }
        )

    missing = sorted(required - actual_columns)

    if missing:
        raise RuntimeError(
            "Missing required benchmark columns: "
            + ", ".join(missing)
        )


def candidate_counts_by_year(
    con,
    spec: DatasetSpec,
    split: str,
) -> list[tuple[int, int]]:
    """
    Candidate counts before deterministic sampling.
    """

    if split not in {"train", "validation"}:
        raise ValueError(
            "Only train and validation are available in "
            "benchmark_dataset.py"
        )

    sql = f"""
        SELECT
            YEAR(date) AS calendar_year,
            COUNT(*) AS n

        FROM silver.research_feature_label_model

        WHERE primary_research_eligible_exchange
          AND {spec.split_column} = {_sql_literal(split)}
          AND {spec.target_column} IS NOT NULL
          AND {spec.return_column} IS NOT NULL
          AND {_feature_complete_predicate()}

        GROUP BY 1
        ORDER BY 1
    """

    return [
        (int(year), int(n))
        for year, n in con.execute(sql).fetchall()
    ]


def allocate_equal_year_quotas(
    year_counts: list[tuple[int, int]],
    requested_total: int,
) -> dict[int, int]:
    """
    Allocate approximately equal observations to every calendar year.

    If one year cannot fill its nominal quota, unused capacity is
    redistributed iteratively to years with remaining observations.
    """

    if requested_total <= 0:
        raise ValueError("requested_total must be positive")

    capacities = {
        year: count
        for year, count in year_counts
        if count > 0
    }

    if not capacities:
        return {}

    target = min(
        requested_total,
        sum(capacities.values()),
    )

    allocation = {
        year: 0
        for year in capacities
    }

    remaining = target
    active = sorted(capacities)

    while remaining > 0 and active:
        base = remaining // len(active)
        remainder = remaining % len(active)

        if base == 0:
            base = 1
            remainder = 0

        used = 0
        next_active = []

        for i, year in enumerate(active):
            desired = base + (
                1
                if i < remainder
                else 0
            )

            available = (
                capacities[year]
                - allocation[year]
            )

            take = min(desired, available)

            allocation[year] += take
            used += take

            if allocation[year] < capacities[year]:
                next_active.append(year)

            if used >= remaining:
                break

        if used == 0:
            break

        remaining -= used
        active = next_active

    return {
        year: n
        for year, n in allocation.items()
        if n > 0
    }


def _quota_values_sql(
    quotas: dict[int, int],
) -> str:
    rows = ",\n            ".join(
        f"({year}, {quota})"
        for year, quota in sorted(quotas.items())
    )

    return f"""
        SELECT *
        FROM (
            VALUES
            {rows}
        ) AS q(calendar_year, quota)
    """


def sampled_query(
    spec: DatasetSpec,
    split: str,
    quotas: dict[int, int],
) -> str:
    """
    Deterministically sample without looking at target class.

    md5() is used rather than random() so rerunning the benchmark produces
    exactly the same security/date membership.
    """

    quota_sql = _quota_values_sql(quotas)

    feature_columns = _sql_identifier_list(FEATURES)

    return f"""
        WITH quota AS (
            {quota_sql}
        ),

        candidates AS (
            SELECT
                security_id,
                date,
                ticker,

                {feature_columns},

                {spec.return_column}
                    AS forward_relative_return,

                {spec.target_column}
                    AS target,

                {spec.target_end_date_column}
                    AS target_end_date,

                YEAR(date) AS calendar_year,

                ROW_NUMBER() OVER (
                    PARTITION BY YEAR(date)
                    ORDER BY
                        MD5(
                            CAST(security_id AS VARCHAR)
                            || '|'
                            || CAST(date AS VARCHAR)
                            || '|'
                            || {_sql_literal(SAMPLING_SEED)}
                            || '|'
                            || CAST({spec.horizon} AS VARCHAR)
                        ),
                        security_id,
                        date
                ) AS sample_rank

            FROM silver.research_feature_label_model

            WHERE primary_research_eligible_exchange
              AND {spec.split_column} = {_sql_literal(split)}
              AND {spec.target_column} IS NOT NULL
              AND {spec.return_column} IS NOT NULL
              AND {_feature_complete_predicate()}
        )

        SELECT
            c.security_id,
            c.date,
            c.ticker,

            {feature_columns},

            c.forward_relative_return,
            c.target,
            c.target_end_date

        FROM candidates c

        JOIN quota q
          ON q.calendar_year = c.calendar_year

        WHERE c.sample_rank <= q.quota

        ORDER BY
            c.date,
            c.security_id
    """


def export_query_to_parquet(
    con,
    query: str,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    con.execute(f"""
        COPY (
            {query}
        )
        TO {_path_literal(output_path)}
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
    """)


def parquet_summary(
    con,
    path: Path,
) -> dict:
    result = con.execute(f"""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT security_id) AS securities,
            MIN(date) AS min_date,
            MAX(date) AS max_date,
            AVG(target) AS positive_rate
        FROM read_parquet({_path_literal(path)})
    """).fetchone()

    return {
        "rows": int(result[0]),
        "securities": int(result[1]),
        "min_date": (
            result[2].isoformat()
            if result[2] is not None
            else None
        ),
        "max_date": (
            result[3].isoformat()
            if result[3] is not None
            else None
        ),
        "positive_rate": (
            float(result[4])
            if result[4] is not None
            else None
        ),
    }


def build_horizon_datasets(
    con,
    spec: DatasetSpec,
    output_dir: Path,
    tabpfn_train_rows: int,
    large_train_rows: int,
    validation_rows: int,
) -> dict:
    """
    Build one horizon's deterministic train/validation datasets.
    """

    horizon_dir = (
        output_dir
        / f"{spec.horizon}d"
    )

    train_counts = candidate_counts_by_year(
        con,
        spec,
        "train",
    )

    validation_counts = candidate_counts_by_year(
        con,
        spec,
        "validation",
    )

    large_train_quotas = allocate_equal_year_quotas(
        train_counts,
        large_train_rows,
    )

    tabpfn_train_quotas = allocate_equal_year_quotas(
        train_counts,
        tabpfn_train_rows,
    )

    validation_quotas = allocate_equal_year_quotas(
        validation_counts,
        validation_rows,
    )

    paths = {
        "train_large":
            horizon_dir / "train_large.parquet",

        "train_tabpfn":
            horizon_dir / "train_tabpfn.parquet",

        "validation":
            horizon_dir / "validation.parquet",
    }

    export_query_to_parquet(
        con,
        sampled_query(
            spec,
            "train",
            large_train_quotas,
        ),
        paths["train_large"],
    )

    export_query_to_parquet(
        con,
        sampled_query(
            spec,
            "train",
            tabpfn_train_quotas,
        ),
        paths["train_tabpfn"],
    )

    export_query_to_parquet(
        con,
        sampled_query(
            spec,
            "validation",
            validation_quotas,
        ),
        paths["validation"],
    )

    summary = {
        "horizon_days": spec.horizon,

        "source":
            "silver.research_feature_label_model",

        "universe":
            "primary_research_eligible_exchange",

        "sampling_seed":
            SAMPLING_SEED,

        "features":
            list(FEATURES),

        "datasets": {
            name: {
                "path": str(path),
                **parquet_summary(
                    con,
                    path,
                ),
            }
            for name, path in paths.items()
        },

        "candidate_rows_by_year": {
            "train": dict(train_counts),
            "validation": dict(validation_counts),
        },

        "sample_quotas_by_year": {
            "train_large":
                large_train_quotas,

            "train_tabpfn":
                tabpfn_train_quotas,

            "validation":
                validation_quotas,
        },
    }

    manifest_path = (
        horizon_dir
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return summary


def build_all(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    tabpfn_train_rows: int = DEFAULT_TABPFN_TRAIN_ROWS,
    large_train_rows: int = DEFAULT_LARGE_TRAIN_ROWS,
    validation_rows: int = DEFAULT_VALIDATION_ROWS,
) -> dict:
    con = connect()

    try:
        validate_source_table(con)

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest = {
            "benchmark_version":
                "v1",

            "test_set_exposed":
                False,

            "horizons":
                {},
        }

        for horizon in HORIZONS:
            print(
                f"\n=== {horizon}d horizon ===",
                flush=True,
            )

            result = build_horizon_datasets(
                con=con,
                spec=DatasetSpec(horizon),
                output_dir=output_dir,
                tabpfn_train_rows=tabpfn_train_rows,
                large_train_rows=large_train_rows,
                validation_rows=validation_rows,
            )

            manifest["horizons"][
                str(horizon)
            ] = result

            for name, details in (
                result["datasets"].items()
            ):
                print(
                    f"{name:15s} "
                    f"rows={details['rows']:,} "
                    f"securities="
                    f"{details['securities']:,} "
                    f"positive_rate="
                    f"{details['positive_rate']:.4f}",
                    flush=True,
                )

        root_manifest = (
            output_dir
            / "manifest.json"
        )

        root_manifest.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        return manifest

    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic train/validation "
            "datasets for benchmark v1."
        )
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--tabpfn-train-rows",
        type=int,
        default=DEFAULT_TABPFN_TRAIN_ROWS,
    )

    parser.add_argument(
        "--large-train-rows",
        type=int,
        default=DEFAULT_LARGE_TRAIN_ROWS,
    )

    parser.add_argument(
        "--validation-rows",
        type=int,
        default=DEFAULT_VALIDATION_ROWS,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    build_all(
        output_dir=args.output_dir,
        tabpfn_train_rows=args.tabpfn_train_rows,
        large_train_rows=args.large_train_rows,
        validation_rows=args.validation_rows,
    )


if __name__ == "__main__":
    main()
