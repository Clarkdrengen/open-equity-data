"""Export the indexed aggregate market cap and a coverage-aware SVG chart."""

from __future__ import annotations

import argparse
import csv
from html import escape
from math import isfinite
from pathlib import Path

from open_equity_data.db import connect


DEFAULT_OUTPUT = Path("artifacts/research/market_cap_candidate")
SQL = (Path(__file__).resolve().parents[2] / "sql/silver"
       / "create_research_aggregate_market_cap_index_candidate.sql")


def _path(values: list[float | None], left: int, top: int,
          width: int, height: int, low: float, high: float) -> str:
    commands = []
    drawing = False
    for i, value in enumerate(values):
        if value is None or not isfinite(float(value)):
            drawing = False
            continue
        x = left + width * i / max(1, len(values) - 1)
        y = top + height * (high - float(value)) / (high - low)
        commands.append(f"{'L' if drawing else 'M'}{x:.2f},{y:.2f}")
        drawing = True
    return " ".join(commands)


def _chart(rows: list[dict]) -> str:
    rows = [r for r in rows if r["cap_index_540"] is not None]
    if not rows:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='120'><text x='20' y='60'>No shared positive base date</text></svg>"
    values = [float(r[f"cap_index_{p}"]) for r in rows
              for p in (365, 540, 730) if r[f"cap_index_{p}"] is not None]
    low, high = min(0.0, min(values)), max(values) * 1.05
    if high == low:
        high += 1.0
    left, width = 85, 1060
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 710" role="img" aria-label="Indexed aggregate market cap and issue coverage">',
        '<rect width="1200" height="710" fill="white"/>',
        '<text x="85" y="35" font-size="21" font-family="sans-serif">Indexed aggregate market cap of covered issues</text>',
        f'<text x="85" y="58" font-size="12" fill="#555" font-family="sans-serif">Base 100 on {escape(str(rows[0]["base_date"]))}; changing membership and coverage affect the level</text>',
    ]
    for y, label in ((90, "Indexed aggregate cap"), (510, "540-day issue coverage")):
        lines.append(f'<text x="85" y="{y}" font-size="13" font-family="sans-serif">{label}</text>')
    for i in range(5):
        y = 110 + i * 90
        v = high - (high - low) * i / 4
        lines.append(f'<line x1="85" x2="1145" y1="{y}" y2="{y}" stroke="#ddd"/>')
        lines.append(f'<text x="75" y="{y+4}" text-anchor="end" font-size="11" font-family="sans-serif">{v:.0f}</text>')
    for policy, color in ((365, "#999999"), (730, "#dd8b32"), (540, "#164d8a")):
        d = _path([r[f"cap_index_{policy}"] for r in rows], left, 110, width, 360, low, high)
        lines.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{3 if policy == 540 else 1.8}"/>')
    coverage = _path([r["issue_coverage_540"] for r in rows], left, 530, width, 100, 0, 1)
    lines.append(f'<path d="{coverage}" fill="none" stroke="#267753" stroke-width="2"/>')
    for y, label in ((530, "100%"), (630, "0%")):
        lines.append(f'<text x="75" y="{y+4}" text-anchor="end" font-size="11" font-family="sans-serif">{label}</text>')
    for i in range(5):
        row = rows[round(i * (len(rows) - 1) / 4)]
        x = left + width * i / 4
        lines.append(f'<text x="{x:.1f}" y="657" text-anchor="middle" font-size="11" font-family="sans-serif">{escape(str(row["date"]))}</text>')
    for i, (policy, color) in enumerate(((365, "#999999"), (540, "#164d8a"), (730, "#dd8b32"))):
        x = 85 + i * 150
        lines.append(f'<line x1="{x}" x2="{x+25}" y1="684" y2="684" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text x="{x+32}" y="688" font-size="12" font-family="sans-serif">{policy} days</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with connect() as con:
        con.execute(SQL.read_text())
        result = con.execute("SELECT * FROM silver.research_aggregate_market_cap_index_candidate ORDER BY date")
        names = [c[0] for c in result.description]
        rows = [dict(zip(names, row)) for row in result.fetchall()]
    if not rows or rows[0]["base_date"] is None:
        raise RuntimeError("No date has positive aggregate cap under all three policies")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "aggregate_market_cap_index.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    chart_path = args.output_dir / "aggregate_market_cap_index.svg"
    chart_path.write_text(_chart(rows))
    print(f"Base date: {rows[0]['base_date']}")
    print(f"Sessions: {len(rows):,}")
    base_row = next(row for row in rows if row["date"] == row["base_date"])
    print(f"Base / last 540-day issue coverage: {base_row['issue_coverage_540']:.1%} / {rows[-1]['issue_coverage_540']:.1%}")
    print(f"Last 540-day aggregate cap: {rows[-1]['aggregate_cap_540']:,.0f}")
    print(f"Last 540-day index: {rows[-1]['cap_index_540']:.2f}")
    year_ends = {row["date"].year: row for row in rows
                  if row["cap_index_540"] is not None}
    print("year-end session | 540-day index | 540-day issue coverage")
    for row in year_ends.values():
        print(f"{row['date']} | {row['cap_index_540']:.2f} | {row['issue_coverage_540']:.1%}")
    print(f"Saved {csv_path} and {chart_path}")


if __name__ == "__main__":
    main()
