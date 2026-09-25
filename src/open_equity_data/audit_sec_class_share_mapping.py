"""Audit missing SEC class-to-symbol links without inferring a mapping.

Only explicit class-member/symbol pairs extracted from the same filing are
evidence. Evidence in other filings is reported with its direction in time;
it is never silently carried backward or forward to a shares observation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from open_equity_data.db import connect


@dataclass(frozen=True)
class Candidate:
    cik: str
    entity_name: str | None
    class_member: str
    filing_date: date
    accession_number: str
    shares_as_of_date: date | None
    trading_symbol: str | None
    symbol_mapping_status: str


def classify_unmapped(rows: list[Candidate]) -> list[tuple[Candidate, str, str | None]]:
    """Return (fact, evidence status, possible symbol) for unmapped facts.

    A possible symbol is diagnostic evidence, never an approved resolution.
    """
    history: dict[tuple[str, str], list[tuple[date, str]]] = defaultdict(list)
    for row in rows:
        if row.symbol_mapping_status == "mapped_unique_symbol" and row.trading_symbol:
            history[(row.cik, row.class_member)].append(
                (row.filing_date, row.trading_symbol.upper())
            )

    result = []
    for row in rows:
        if row.symbol_mapping_status != "no_trading_symbol":
            continue

        observations = history[(row.cik, row.class_member)]
        symbols = {symbol for _, symbol in observations}
        if not symbols:
            result.append((row, "no_symbol_evidence", None))
        elif len(symbols) != 1:
            result.append((row, "multiple_historical_symbols", None))
        else:
            symbol = next(iter(symbols))
            earlier = any(d <= row.filing_date for d, _ in observations)
            later = any(d >= row.filing_date for d, _ in observations)
            if earlier and later:
                status = "bracketed_same_symbol"
            elif earlier:
                status = "earlier_evidence_only"
            else:
                status = "later_evidence_only"
            result.append((row, status, symbol))
    return result


def main() -> None:
    con = connect()
    try:
        records = con.execute("""
            SELECT cik, entity_name, class_member, filing_date,
                   accession_number, shares_as_of_date, trading_symbol,
                   symbol_mapping_status
            FROM silver.sec_class_share_candidate
            WHERE symbol_mapping_status IN (
                'mapped_unique_symbol', 'no_trading_symbol'
            )
            ORDER BY cik, class_member, filing_date, accession_number
        """).fetchall()
    finally:
        con.close()

    rows = [Candidate(*record) for record in records]
    audit = classify_unmapped(rows)
    totals = Counter(status for _, status, _ in audit)

    print(f"Mapped source facts: {sum(r.symbol_mapping_status == 'mapped_unique_symbol' for r in rows):,}")
    print(f"Unmapped source facts: {len(audit):,}")
    print("\nEVIDENCE STATUS (fact counts)")
    for status, count in totals.most_common():
        print(f"  {status:30s} {count:6,d}")

    by_member: dict[tuple[str, str, str], list[tuple[Candidate, str, str | None]]] = defaultdict(list)
    for item in audit:
        row, status, _ = item
        by_member[(row.cik, row.entity_name or "", row.class_member)].append(item)

    print("\nUNMAPPED ISSUER / CLASS MEMBERS")
    print("cik | issuer | class_member | facts | evidence_status | possible_symbol | first_filing | last_filing")
    for (cik, issuer, member), items in sorted(
        by_member.items(), key=lambda pair: (-len(pair[1]), pair[0])
    ):
        statuses = ",".join(sorted({status for _, status, _ in items}))
        symbols = ",".join(sorted({symbol for _, _, symbol in items if symbol}))
        dates = [row.filing_date for row, _, _ in items]
        print(
            f"{cik} | {issuer} | {member} | {len(items)} | {statuses} | "
            f"{symbols or '-'} | {min(dates)} | {max(dates)}"
        )

    print("\nThese are evidence categories, not approved ticker mappings.")


if __name__ == "__main__":
    main()
