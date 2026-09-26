from datetime import date
from pathlib import Path

import duckdb
import pytest

from open_equity_data.export_aggregate_market_cap_index import _chart


SQL = (Path(__file__).resolve().parents[1] / "sql/silver"
       / "create_research_aggregate_market_cap_index_candidate.sql")


def test_shared_base_index_preserves_coverage_and_membership_changes():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.security_daily_market_cap_candidate AS
        SELECT * FROM (VALUES
          (DATE '2024-01-01', NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE),
          (DATE '2024-01-02', 100.0, 100.0, 100.0),
          (DATE '2024-01-02', NULL::DOUBLE, 200.0, 200.0),
          (DATE '2024-01-03', 110.0, 110.0, 110.0),
          (DATE '2024-01-03', NULL::DOUBLE, 220.0, 220.0),
          (DATE '2024-01-03', NULL::DOUBLE, NULL::DOUBLE, 900.0)
        ) v(date, market_cap_365, market_cap_540, market_cap_730)
    """)
    con.execute(SQL.read_text())
    result = con.execute("""
        SELECT date, base_date, covered_issues_540, issue_coverage_540,
               cap_index_365, cap_index_540, cap_index_730
        FROM silver.research_aggregate_market_cap_index_candidate ORDER BY date
    """).fetchall()
    assert [r[1] for r in result] == [date(2024, 1, 2)] * 3
    assert result[0][5] is None
    assert result[1][5] == pytest.approx(100.0)
    assert result[2][5] == pytest.approx(110.0)
    assert result[2][6] == pytest.approx(100.0 * 1230 / 300)
    assert result[2][2:4] == (2, pytest.approx(2 / 3))

    names = ["date", "base_date", "issue_coverage_540",
             "cap_index_365", "cap_index_540", "cap_index_730"]
    svg = _chart([dict(zip(names, (r[0], r[1], r[3], r[4], r[5], r[6])))
                  for r in result])
    assert "2024-01-02" in svg
    assert "<path" in svg
