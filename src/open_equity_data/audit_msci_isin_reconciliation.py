"""Profile Bronze-derived Silver MSCI rows and compare names by ISIN.

The supplied file's units and provenance are not asserted by this program.
Text matching is diagnostic, never an identity approval.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from open_equity_data.db import connect


DEFAULT_OUTPUT = Path("artifacts/research/msci_isin_reconciliation")


@dataclass
class IsinHistory:
    names: set[str] = field(default_factory=set)
    first_date: str = "9999-99-99"
    last_date: str = ""
    last_name: str = ""
    last_cap: float | None = None
    rows: int = 0
    conflicting_duplicate: bool = False


def valid_isin(isin: str) -> bool:
    """ISO 6166 format plus Luhn check digit; no security semantics implied."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in isin)
    return sum(divmod(int(c) * (2 if i % 2 else 1), 10)[0]
               + divmod(int(c) * (2 if i % 2 else 1), 10)[1]
               for i, c in enumerate(digits[::-1])) % 10 == 0


def normalized_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def read_panel(con, digest: str):
    histories: dict[str, IsinHistory] = defaultdict(IsinHistory)
    counters: Counter = Counter()
    invalid: Counter = Counter()
    seen: dict[tuple[str, str], tuple[str, float]] = {}
    duplicate_rows = []
    reader = con.execute("""
        SELECT source_row_number, raw_date, raw_isin, raw_company_name,
               raw_mktcap, field_count, parse_status
        FROM silver.msci_usa_observation
        WHERE source_sha256 = ? ORDER BY source_row_number
    """, [digest]).fetchall()
    for line_number, date, raw_isin, name, raw_cap, width, status in reader:
            counters["raw_rows"] += 1
            if width not in (5, 6):
                counters["unexpected_width"] += 1
                continue
            if width == 6:
                counters["unquoted_name_commas"] += 1
            isin = (raw_isin or "").strip().upper()
            name = (name or "").strip()
            raw_cap = (raw_cap or "").strip()
            if status == "na_padding":
                counters["na_padding_rows"] += 1
                continue
            try:
                cap = float(raw_cap)
            except ValueError:
                counters["nonnumeric_cap_rows"] += 1
                continue
            counters["numeric_cap_rows"] += 1
            if not isin:
                counters["blank_isin_rows"] += 1
                continue
            if not valid_isin(isin):
                counters["invalid_isin_rows"] += 1
                invalid[isin] += 1
                continue
            h = histories[isin]
            h.rows += 1
            h.names.add(name)
            h.first_date = min(date, h.first_date)
            if date > h.last_date:
                h.last_date, h.last_name, h.last_cap = date, name, cap
            key = date, isin
            if key in seen:
                counters["duplicate_date_isin_rows"] += 1
                previous_name, previous_cap = seen[key]
                if (previous_name, previous_cap) != (name, cap):
                    h.conflicting_duplicate = True
                duplicate_rows.append((date, isin, previous_name, previous_cap, name, cap))
            else:
                seen[key] = name, cap
            counters["valid_isin_rows"] += 1
    counters["distinct_valid_isins"] = len(histories)
    counters["isins_with_multiple_names"] = sum(len(h.names) > 1 for h in histories.values())
    return histories, counters, invalid, duplicate_rows


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(rows)


def references(con):
    names = defaultdict(set)
    tickers = defaultdict(set)
    security_ids = defaultdict(set)
    for isin, name, code in con.execute("""
        SELECT UPPER(TRIM(isin)), name, code
        FROM bronze.eodhd_symbol_reference
        WHERE isin IS NOT NULL AND TRIM(isin) <> ''
    """).fetchall():
        if name:
            names[isin].add(name)
        if code:
            tickers[isin].add(code)
    for isin, security_id, ticker in con.execute("""
        SELECT UPPER(TRIM(resolved_isin)), security_id, ticker
        FROM silver.security_ticker_reference_resolution
        WHERE resolved_isin IS NOT NULL AND TRIM(resolved_isin) <> ''
    """).fetchall():
        security_ids[isin].add(str(security_id))
        tickers[isin].add(ticker)
    return names, tickers, security_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", help="Required if multiple MSCI source files are archived")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile-only", action="store_true",
                        help="Skip EODHD/project reference comparison")
    args = parser.parse_args()
    with connect(read_only=True) as con:
        if args.source_sha256:
            digest = args.source_sha256
        else:
            sources = con.execute("SELECT source_sha256 FROM bronze.msci_usa_source_file").fetchall()
            if len(sources) != 1:
                raise ValueError("Specify --source-sha256 when Bronze holds multiple source files")
            digest = sources[0][0]
        histories, counts, invalid, duplicates = read_panel(con, digest)
        if not counts["raw_rows"]:
            raise ValueError("No Silver rows for source SHA-256; run build_msci_usa_silver")
        if not args.profile_only:
            names, tickers, security_ids = references(con)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    profile = args.output_dir / "msci_isin_name_profile.csv"
    write_csv(profile,
              ["isin", "first_date", "last_date", "latest_name", "all_names",
               "name_variants", "rows", "latest_mktcap_as_supplied", "conflicting_duplicate"],
              ((isin, h.first_date, h.last_date, h.last_name,
                " | ".join(sorted(h.names)), len(h.names), h.rows, h.last_cap,
                h.conflicting_duplicate)
               for isin, h in sorted(histories.items())))
    write_csv(args.output_dir / "invalid_isins.csv", ["isin", "rows"],
              sorted(invalid.items(), key=lambda item: (-item[1], item[0])))
    write_csv(args.output_dir / "duplicate_date_isin.csv",
              ["date", "isin", "first_name", "first_cap", "other_name", "other_cap"],
              duplicates)
    print("Source rows and ISIN checks:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value:,}")
    print(f"Saved {profile}")
    if args.profile_only:
        return
    compared = args.output_dir / "msci_vs_project_isin_names.csv"
    status_counts = Counter()
    def comparisons():
        for isin, h in sorted(histories.items()):
            eodhd = names.get(isin, set())
            if not eodhd:
                status = "no_eodhd_isin"
                score = None
            else:
                msci_names = {normalized_name(n) for n in h.names}
                eodhd_names = {normalized_name(n) for n in eodhd}
                score = max(SequenceMatcher(None, a, b).ratio()
                            for a in msci_names for b in eodhd_names)
                status = ("exact_normalized_alias" if msci_names & eodhd_names
                          else "name_review")
            status_counts[status] += 1
            yield (isin, h.first_date, h.last_date, h.last_name, h.last_cap,
                   " | ".join(sorted(h.names)),
                   " | ".join(sorted(eodhd)),
                   " | ".join(sorted(tickers.get(isin, set()))),
                   " | ".join(sorted(security_ids.get(isin, set()))),
                   status, score, h.conflicting_duplicate)
    write_csv(compared,
              ["isin", "msci_first_date", "msci_last_date", "msci_latest_name",
               "msci_latest_mktcap_as_supplied", "msci_all_names", "eodhd_names",
               "project_tickers", "security_ids",
               "name_status", "best_name_similarity", "msci_conflicting_duplicate"],
              comparisons())
    print("Name comparison by exact ISIN (text matches do not approve identities):")
    for key, value in sorted(status_counts.items()):
        print(f"  {key}: {value:,}")
    print(f"  with_project_security_id: {sum(bool(security_ids.get(i)) for i in histories):,}")
    print(f"Saved {compared}")


if __name__ == "__main__":
    main()
